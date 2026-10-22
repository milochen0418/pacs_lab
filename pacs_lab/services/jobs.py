"""Long work (starting a PACS, putting data in) runs in a thread; the pages poll its snapshot."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import secrets
import threading
import uuid
from pathlib import Path

from pydicom import dcmread

from pacs_lab.services import checks, docker_lab, library, load, reid, starter
from pacs_lab.services.docker_lab import LabError
from pacs_lab.services.kinds import KINDS, LabPacs, aet_for
from pacs_lab.services.paths import data_dir

CREATE_STEPS = ["step_image", "step_container", "step_ready", "step_fetch", "step_load", "step_check"]
LOAD_STEPS = ["step_fetch", "step_load", "step_check"]


@dataclasses.dataclass
class DataChoice:
    starter: list[str] = dataclasses.field(default_factory=list)  # starter study keys
    library: list[str] = dataclasses.field(default_factory=list)  # series UIDs in the shared folder
    relabel: bool = True  # new UIDs and made-up patients

    @property
    def empty(self) -> bool:
        return not (self.starter or self.library)


@dataclasses.dataclass
class Step:
    key: str
    state: str = "waiting"  # waiting | running | done | failed | skipped
    detail: str = ""


class _Skip(Exception):
    pass


class Job:
    def __init__(self, steps: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.steps = [Step(k) for k in steps]
        self.error = ""  # a LabError key, "key:detail", or "unexpected:..."
        self.done = False
        self.pacs_name = ""
        self.patients: list[dict] = []
        self.checks: list[checks.Result] = []
        self.version = 0
        self._lock = threading.Lock()
        self._current: Step | None = None

    @contextlib.contextmanager
    def step(self, key: str):
        s = next(x for x in self.steps if x.key == key)
        with self._lock:
            s.state, self._current = "running", s
            self.version += 1
        try:
            yield s
        except _Skip:
            s.state = "skipped"
        except BaseException:
            s.state = "failed"
            raise
        else:
            s.state = "done"
        finally:
            with self._lock:
                self._current = None
                self.version += 1

    def skip(self) -> None:
        raise _Skip()

    def detail(self, text: str) -> None:
        with self._lock:
            if self._current is not None:
                self._current.detail = text
                self.version += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id, "version": self.version, "done": self.done, "error": self.error,
                "pacs": self.pacs_name, "steps": [dataclasses.asdict(s) for s in self.steps],
                "patients": list(self.patients), "checks": list(self.checks),
            }


_JOBS: dict[str, Job] = {}


def get(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def _launch(job: Job, fn, *args) -> str:
    _JOBS[job.id] = job

    def run() -> None:
        try:
            fn(job, *args)
        except LabError as exc:
            job.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            logging.exception("PACS lab job failed")
            job.error = f"unexpected:{exc}"
        finally:
            job.done = True
            job.version += 1

    threading.Thread(target=run, name=f"pacs-lab-{job.id}", daemon=True).start()
    return job.id


def start_create(kind: str, label: str, explorer_at: str, data: DataChoice) -> str:
    return _launch(Job(CREATE_STEPS), _create, kind, label, explorer_at, data)


def start_load(name: str, data: DataChoice) -> str:
    return _launch(Job(LOAD_STEPS), _load_into, name, data)


# -- the work ---------------------------------------------------------------------------

def _password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def _create(job: Job, kind: str, label: str, explorer_at: str, data: DataChoice) -> None:
    c = docker_lab.client()
    with job.step("step_image"):
        docker_lab.ensure_image(c, kind, job.detail)
    with job.step("step_container"):
        number = docker_lab.next_number(c, kind)
        name = f"{docker_lab.PREFIX}-{kind}-{number}"
        p = docker_lab.run_pacs(
            c, kind=kind, name=name, label=label.strip() or f"{KINDS[kind].label_prefix} {number}",
            aet=aet_for(kind, number), password=_password(), explorer_at=explorer_at,
        )
        job.pacs_name = p.name
        job.detail(p.name)
    with job.step("step_ready"):
        docker_lab.wait_running(c, p.name)
        host, http_port, dicom_port = docker_lab.reach(c, p)
        if not checks.wait_ready(p, host, http_port, dicom_port):
            raise LabError("not_ready:" + docker_lab.logs(c, p.name, 15))
    _fill(job, c, p, data)


def _load_into(job: Job, name: str, data: DataChoice) -> None:
    c = docker_lab.client()
    p = docker_lab.get_pacs(c, name)
    if p is None:
        raise LabError("not_found")
    if p.status != "running":
        raise LabError("not_running")
    job.pacs_name = p.name
    _fill(job, c, p, data)


_BOOK_LOCK = threading.Lock()


def _book_path() -> Path:
    return data_dir() / "patients.json"


def patient_book() -> tuple[dict[str, dict], int]:
    """The made-up patients, the same in every practice PACS: (real ID -> patient, next number)."""
    try:
        data = json.loads(_book_path().read_text())
        return data.get("patients", {}), int(data.get("next", 1))
    except (OSError, ValueError):
        return {}, 1


def _save_book(book: dict[str, dict], next_number: int) -> None:
    tmp = _book_path().with_suffix(".tmp")
    tmp.write_text(json.dumps({"patients": book, "next": next_number}, indent=1, ensure_ascii=False))
    tmp.replace(_book_path())


def _fill(job: Job, c, p: LabPacs, data: DataChoice) -> None:
    host, http_port, dicom_port = docker_lab.reach(c, p)
    paths: list[Path] = []
    with job.step("step_fetch"):
        if data.empty:
            job.skip()
        if data.starter:
            studies = [s for s in starter.STARTER if s.key in data.starter]
            got = starter.download(studies, lambda d, t: job.detail(f"{d / 1e6:.0f} / {t / 1e6:.0f} MB") if t else None)
            paths += [f for files in got.values() for f in files]
        if data.library:
            paths += [f for files in library.files_of(data.library).values() for f in files]
        job.detail(f"{len(paths)}")
    with job.step("step_load"):
        if not paths:
            job.skip()
        contexts: dict[str, set[str]] = {}
        real: dict[str, dict] = {}
        with _BOOK_LOCK:
            book, first = patient_book()
            relabel = reid.Relabel(book=book, first_number=first) if data.relabel else None
            for path in paths:
                h = dcmread(path, stop_before_pixels=True)
                contexts.setdefault(str(h.SOPClassUID), set()).add(str(h.file_meta.TransferSyntaxUID))
                if relabel:
                    relabel.learn(h)
                else:
                    pid = str(h.get("PatientID", "") or "")
                    real.setdefault(pid, {"id": pid, "name": str(h.get("PatientName", "") or ""), "studies": []})
            if relabel:
                _save_book(relabel.book, relabel.next_number)

        def datasets():
            for path in paths:
                ds = dcmread(path)
                yield relabel.apply(ds) if relabel else ds

        total = len(paths)
        progress = lambda n: job.detail(f"{n} / {total}")  # noqa: E731
        if KINDS[p.kind].http_port:
            load.to_orthanc(
                f"http://{host}:{http_port}", p.password, (reid.to_bytes(ds) for ds in datasets()), progress
            )
        else:
            load.to_dimse(host, dicom_port, p.aet, contexts, datasets(), progress)
        job.patients = list(relabel.patients.values()) if relabel else list(real.values())
    with job.step("step_check"):
        job.checks = checks.run(p, host, http_port, dicom_port)


def studies_in(c, p: LabPacs) -> list[dict]:
    """What the PACS holds, as DICOM Data Explorer would find it (C-FIND as DDE_EXPLORER)."""
    host, _http_port, dicom_port = docker_lab.reach(c, p)
    return checks.list_studies(host, dicom_port, p.aet)
