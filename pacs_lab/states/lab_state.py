"""The whole app's state: the list, the wizard, one PACS's page, and the running job.

One state class, so every text follows the language switch (computed vars
read ``lang`` and the raw data side by side).
"""

from __future__ import annotations

import asyncio
import dataclasses

import reflex as rx

from pacs_lab.i18n import TEXTS, error_text, tr
from pacs_lab.services import docker_lab, jobs, library, starter
from pacs_lab.services.docker_lab import LabError
from pacs_lab.services.kinds import APPSTORE, KINDS, MAC, LabPacs, explorer_cards

KIND_ORDER = ["orthanc", "orthanc-strict", "mini"]


@dataclasses.dataclass
class PacsRow:
    name: str = ""
    label: str = ""
    kind: str = ""
    aet: str = ""
    status: str = ""
    dicom_port: int = 0
    http_port: int = 0
    web_page: str = ""
    explorer_at: str = ""


@dataclasses.dataclass
class KindRow:
    id: str = ""
    memory: str = ""
    dicomweb: bool = False
    can_get: bool = False
    web: bool = False


@dataclasses.dataclass
class StarterRow:
    key: str = ""
    detail: str = ""  # collection · kinds · images · licence
    mb: str = ""


@dataclasses.dataclass
class LibRow:
    uid: str = ""
    modality: str = ""
    description: str = ""
    collection: str = ""
    images: int = 0
    mb: str = ""
    detail: str = ""  # collection · images, in the page's language


@dataclasses.dataclass
class StepRow:
    label: str = ""
    state: str = ""
    detail: str = ""


@dataclasses.dataclass
class LineRow:
    state: str = ""
    text: str = ""


@dataclasses.dataclass
class PatientRow:
    id: str = ""
    name: str = ""
    studies: str = ""


@dataclasses.dataclass
class FieldRow:
    key: str = ""
    label: str = ""
    value: str = ""
    hint: str = ""
    secret: bool = False


@dataclasses.dataclass
class CardRow:
    title: str = ""
    fields: list[FieldRow] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class StudyRow:
    patient_id: str = ""
    patient_name: str = ""
    date: str = ""
    description: str = ""
    modalities: str = ""
    images: str = ""


def _row(p: LabPacs) -> PacsRow:
    return PacsRow(p.name, p.label, p.kind, p.aet, p.status, p.dicom_port, p.http_port, p.web_page, p.explorer_at)


def _name(pn: str) -> str:
    return " ".join(pn.replace("^", " ").split())


def _date(da: str) -> str:
    return f"{da[:4]}-{da[4:6]}-{da[6:8]}" if len(da) == 8 and da.isdigit() else da


class LabState(rx.State):
    lang: str = rx.LocalStorage("zh", name="pacs_lab_lang")

    # the list
    pacs: list[PacsRow] = []
    explorer_where: str = ""
    docker_error: str = ""
    busy: str = ""
    delete_name: str = ""
    delete_label: str = ""

    # the wizard
    wiz_step: int = 1
    wiz_kind: str = "orthanc"
    wiz_label: str = ""
    wiz_place: str = APPSTORE
    pick_starter: list[str] = ["kidney", "lung", "xray"]
    pick_library: list[str] = []
    relabel: bool = True
    library_rows: list[LibRow] = []
    library_state: str = ""  # "" | "none" | "off"

    # the running job (creating a PACS, or adding images)
    job_id: str = ""
    job: dict = {}

    # one PACS
    d: PacsRow = PacsRow()
    d_password: str = ""
    studies: list[StudyRow] = []
    studies_state: str = ""  # "" | "loading" | "off"
    logs: str = ""
    add_open: bool = False
    revealed: list[str] = []

    # -- words ----------------------------------------------------------------------------

    @rx.var
    def t(self) -> dict[str, str]:
        return {**TEXTS["en"], **TEXTS.get(self.lang, TEXTS["zh"])}

    @rx.event
    def toggle_lang(self):
        self.lang = "en" if self.lang == "zh" else "zh"

    @rx.var
    def docker_error_text(self) -> str:
        return error_text(self.lang, self.docker_error)

    @rx.var
    def where_text(self) -> str:
        if not self.explorer_where:
            return ""
        return tr(self.lang, "where_appstore" if self.explorer_where == APPSTORE else "where_mac")

    @rx.var
    def kinds(self) -> list[KindRow]:
        return [
            KindRow(k, tr(self.lang, "kind_memory", mb=int(KINDS[k].memory.rstrip("m"))),
                    bool(KINDS[k].http_port), KINDS[k].retrieve == "C-GET", bool(KINDS[k].http_port))
            for k in KIND_ORDER
        ]

    @rx.var
    def starter_rows(self) -> list[StarterRow]:
        return [
            StarterRow(
                s.key,
                " · ".join((s.collection, " + ".join(x.modality for x in s.series),
                            tr(self.lang, "n_images", n=sum(x.images for x in s.series)), s.license)),
                f"{s.mb:.0f} MB",
            )
            for s in starter.STARTER
        ]

    @rx.var
    def library_view(self) -> list[LibRow]:
        return [
            dataclasses.replace(r, detail=" · ".join(x for x in (r.collection, tr(self.lang, "n_images", n=r.images)) if x))
            for r in self.library_rows
        ]

    # -- the list -------------------------------------------------------------------------

    @rx.event(background=True)
    async def load_home(self):
        try:
            found, where = await asyncio.to_thread(self._read_list)
        except LabError as exc:
            async with self:
                self.docker_error, self.pacs = str(exc), []
            return
        async with self:
            self.docker_error, self.pacs, self.explorer_where = "", [_row(p) for p in found], where

    @staticmethod
    def _read_list() -> tuple[list[LabPacs], str]:
        c = docker_lab.client()
        return docker_lab.list_pacs(c), docker_lab.explorer_where(c)

    @rx.event(background=True)
    async def power(self, name: str, on: bool):
        async with self:
            self.busy = name
        try:
            c = await asyncio.to_thread(docker_lab.client)
            await asyncio.to_thread(docker_lab.start if on else docker_lab.stop, c, name)
            message = tr(self.lang, "started" if on else "stopped")
        except (LabError, Exception) as exc:  # noqa: BLE001 - shown as a toast
            message = error_text(self.lang, str(exc) if isinstance(exc, LabError) else f"unexpected:{exc}")
        async with self:
            self.busy = ""
        yield rx.toast.info(message)
        yield LabState.load_home
        yield LabState.reload_detail

    @rx.event
    def ask_delete(self, name: str, label: str):
        self.delete_name, self.delete_label = name, label

    @rx.event
    def cancel_delete(self):
        self.delete_name = self.delete_label = ""

    @rx.event(background=True)
    async def confirm_delete(self):
        async with self:
            name, self.busy = self.delete_name, self.delete_name
            self.delete_name = self.delete_label = ""
        try:
            c = await asyncio.to_thread(docker_lab.client)
            await asyncio.to_thread(docker_lab.remove, c, name)
            message = tr(self.lang, "deleted")
        except Exception as exc:  # noqa: BLE001
            message = error_text(self.lang, str(exc) if isinstance(exc, LabError) else f"unexpected:{exc}")
        async with self:
            self.busy = ""
            on_detail = self.d.name == name
        yield rx.toast.info(message)
        if on_detail:
            yield rx.redirect("/")
        else:
            yield LabState.load_home

    # -- the wizard -----------------------------------------------------------------------

    @rx.event(background=True)
    async def load_wizard(self):
        async with self:
            job = jobs.get(self.job_id) if self.job_id else None
            if job is not None and not job.done and self.wiz_step == 4:
                running = True
            else:
                running = False
                self.wiz_step, self.wiz_kind, self.wiz_label, self.job_id, self.job = 1, "orthanc", "", "", {}
                self.pick_starter = [s.key for s in starter.STARTER]
                self.pick_library, self.relabel = [], True
        if running:
            yield LabState.follow
            return
        try:
            c = await asyncio.to_thread(docker_lab.client)
            where = await asyncio.to_thread(docker_lab.explorer_where, c)
            async with self:
                self.docker_error, self.explorer_where, self.wiz_place = "", where, where
        except LabError as exc:
            async with self:
                self.docker_error = str(exc)
        yield LabState.load_library

    @rx.event(background=True)
    async def load_library(self):
        try:
            rows = await asyncio.to_thread(library.list_series)
            state = "" if rows else "none"
        except Exception:  # noqa: BLE001 - no shared folder here
            rows, state = [], "off"
        async with self:
            self.library_rows = [
                LibRow(r.uid, r.modality, r.description or "—", r.collection, r.images, f"{r.mb:g} MB") for r in rows
            ]
            self.library_state = state
            self.pick_library = [u for u in self.pick_library if any(r.uid == u for r in rows)]

    @rx.event
    def choose_kind(self, kind: str):
        if kind in KINDS:
            self.wiz_kind = kind

    @rx.event
    def set_label(self, value: str):
        self.wiz_label = value[:60]

    @rx.event
    def set_place(self, place: str):
        if place in (APPSTORE, MAC):
            self.wiz_place = place

    @rx.event
    def toggle_starter(self, key: str):
        self.pick_starter = [k for k in self.pick_starter if k != key] if key in self.pick_starter else [*self.pick_starter, key]

    @rx.event
    def toggle_library(self, uid: str):
        self.pick_library = [u for u in self.pick_library if u != uid] if uid in self.pick_library else [*self.pick_library, uid]

    @rx.event
    def toggle_relabel(self):
        self.relabel = not self.relabel

    @rx.event
    def wiz_go(self, step: int):
        if 1 <= step <= 3 and not (self.job and not self.job.get("done")):
            self.wiz_step = step

    @rx.var
    def picked_mb(self) -> str:
        mb = sum(s.mb for s in starter.STARTER if s.key in self.pick_starter)
        mb += sum(float(r.mb.split()[0]) for r in self.library_rows if r.uid in self.pick_library)
        return f"{mb:.0f}"

    @rx.var
    def picked_series(self) -> int:
        return sum(len(s.series) for s in starter.STARTER if s.key in self.pick_starter) + len(self.pick_library)

    @rx.var
    def summary_data(self) -> str:
        if not self.picked_series:
            return tr(self.lang, "summary_nodata")
        return tr(self.lang, "summary_data", n=self.picked_series, mb=self.picked_mb)

    @rx.var
    def default_label(self) -> str:
        """The name the job gives when none is typed: numbered like its AE title."""
        taken, n = {p.aet for p in self.pacs}, 1
        while f"{KINDS[self.wiz_kind].aet_prefix}_{n}" in taken:
            n += 1
        return f"{KINDS[self.wiz_kind].label_prefix} {n}"

    def _choice(self) -> jobs.DataChoice:
        return jobs.DataChoice(starter=list(self.pick_starter), library=list(self.pick_library), relabel=self.relabel)

    @rx.event
    def create(self):
        self.job_id = jobs.start_create(self.wiz_kind, self.wiz_label, self.wiz_place, self._choice())
        self.job, self.wiz_step = {}, 4
        return LabState.follow

    # -- following a job --------------------------------------------------------------------

    @rx.event(background=True)
    async def follow(self):
        version = -1
        while True:
            async with self:
                job = jobs.get(self.job_id)
            if job is None:
                return
            snap = job.snapshot()
            if snap["version"] != version:
                version = snap["version"]
                async with self:
                    if self.job_id != snap["id"]:
                        return
                    self.job = snap
            if snap["done"]:
                break
            await asyncio.sleep(0.6)
        yield LabState.load_home
        yield LabState.reload_detail

    @rx.var
    def job_running(self) -> bool:
        return bool(self.job) and not self.job.get("done", False)

    @rx.var
    def job_done_ok(self) -> bool:
        return bool(self.job.get("done")) and not self.job.get("error")

    @rx.var
    def job_failed(self) -> bool:
        return bool(self.job.get("done")) and bool(self.job.get("error"))

    @rx.var
    def job_steps(self) -> list[StepRow]:
        return [StepRow(tr(self.lang, s["key"]), s["state"], s["detail"]) for s in self.job.get("steps", [])]

    @rx.var
    def job_error(self) -> str:
        return error_text(self.lang, self.job.get("error", ""))

    @rx.var
    def job_checks(self) -> list[LineRow]:
        return [LineRow(state, tr(self.lang, key, **params)) for state, key, params in self.job.get("checks", [])]

    @rx.var
    def job_patients(self) -> list[PatientRow]:
        return [
            PatientRow(p.get("id", ""), _name(p.get("name", "")), ", ".join(x for x in p.get("studies", []) if x))
            for p in self.job.get("patients", [])
        ]

    @rx.var
    def job_pacs(self) -> str:
        return self.job.get("pacs", "")

    # -- one PACS ---------------------------------------------------------------------------

    @rx.event
    def load_detail(self):
        path = str(self.router.url.path or "")
        name = path.rstrip("/").rsplit("/", 1)[-1]
        if self.d.name != name:
            self.d, self.d_password, self.studies, self.logs, self.revealed = PacsRow(name=name), "", [], "", []
        self.add_open = False
        return LabState.reload_detail

    @rx.event(background=True)
    async def reload_detail(self):
        async with self:
            name = self.d.name
        if not name:
            return
        try:
            c = await asyncio.to_thread(docker_lab.client)
            p = await asyncio.to_thread(docker_lab.get_pacs, c, name)
        except LabError as exc:
            async with self:
                self.docker_error = str(exc)
            return
        if p is None:
            yield rx.redirect("/")
            return
        async with self:
            self.docker_error, self.d, self.d_password = "", _row(p), p.password
            self.studies_state = "loading" if p.status == "running" else "off"
        rows: list[StudyRow] = []
        if p.status == "running":
            try:
                found = await asyncio.to_thread(jobs.studies_in, c, p)
                rows = [
                    StudyRow(s["patient_id"], _name(s["patient_name"]), _date(s["date"]), s["description"],
                             s["modalities"], s["images"])
                    for s in found
                ]
            except Exception:  # noqa: BLE001 - shown as empty
                rows = []
        async with self:
            if self.d.name == name:
                self.studies = rows
                self.studies_state = "" if p.status == "running" else "off"

    @rx.var
    def cards(self) -> list[CardRow]:
        if not self.d.kind:
            return []
        p = LabPacs(
            name=self.d.name, label=self.d.label, kind=self.d.kind, aet=self.d.aet, dicom_port=self.d.dicom_port,
            http_port=self.d.http_port, password=self.d_password, explorer_at=self.d.explorer_at,
        )
        return [
            CardRow(
                tr(self.lang, card.title),
                [
                    FieldRow(f"{i}-{j}", f.label, f.value, tr(self.lang, f.hint) if f.hint else "", f.secret)
                    for j, f in enumerate(card.fields)
                ],
            )
            for i, card in enumerate(explorer_cards(p))
        ]

    @rx.event
    def reveal(self, key: str):
        self.revealed = [k for k in self.revealed if k != key] if key in self.revealed else [*self.revealed, key]

    @rx.event
    def copy(self, value: str):
        return [rx.set_clipboard(value), rx.toast.success(tr(self.lang, "copied"), duration=1500)]

    @rx.event(background=True)
    async def switch_place(self, place: str):
        async with self:
            name, self.busy = self.d.name, self.d.name
        try:
            c = await asyncio.to_thread(docker_lab.client)
            await asyncio.to_thread(docker_lab.recreate, c, name, explorer_at=place)
            p = await asyncio.to_thread(docker_lab.get_pacs, c, name)
            host, http_port, dicom_port = await asyncio.to_thread(docker_lab.reach, c, p)
            from pacs_lab.services import checks

            await asyncio.to_thread(checks.wait_ready, p, host, http_port, dicom_port, 60)
            message = tr(self.lang, "switched")
        except Exception as exc:  # noqa: BLE001
            message = error_text(self.lang, str(exc) if isinstance(exc, LabError) else f"unexpected:{exc}")
        async with self:
            self.busy = ""
        yield rx.toast.info(message)
        yield LabState.reload_detail

    @rx.event(background=True)
    async def show_logs(self):
        async with self:
            name = self.d.name
        try:
            c = await asyncio.to_thread(docker_lab.client)
            text = await asyncio.to_thread(docker_lab.logs, c, name, 150)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
        async with self:
            self.logs = text or "—"

    @rx.event
    def set_add_open(self, value: bool):
        if self.job_running:
            return
        self.add_open = value
        if value:
            self.job_id, self.job = "", {}
            return LabState.load_library

    @rx.event
    def add_data(self):
        self.job_id = jobs.start_load(self.d.name, self._choice())
        self.job = {}
        return LabState.follow
