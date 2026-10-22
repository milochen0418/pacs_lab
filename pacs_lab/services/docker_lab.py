"""Starting, listing and removing the practice PACS containers (docker-py).

The lab talks to Docker through its socket: /var/run/docker.sock, which the
App Store catalog mounts into the app's container, or Docker Desktop's on a Mac.
Only containers carrying the ``pacs-lab.kind`` label are ever touched.
"""

from __future__ import annotations

import io
import os
import socket
import tarfile
import time
from datetime import datetime, timezone
from importlib import resources
from typing import Callable

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

from pacs_lab.services.kinds import (
    APPSTORE, EXPLORER_CONTAINER, HOST_PORT_BASE, KINDS, MAC, MINI_IMAGE, LabPacs,
    container_command, container_env,
)

PREFIX = "pacs-lab"
LABEL_KIND = f"{PREFIX}.kind"
RE_DDNS_NETWORK = "re_ddns_ddns-net"
PKG_CACHE = "http://pkg-cache:3142"

Progress = Callable[[str], None]


class LabError(Exception):
    """A problem to show as it is: the message is for the user."""


def client() -> docker.DockerClient:
    try:
        c = docker.from_env(timeout=120)
        c.ping()
        return c
    except DockerException as exc:
        raise LabError("no_docker") from exc


def own_container(c: docker.DockerClient):
    """The lab's own container, when it runs in one (its hostname is its name)."""
    if not os.path.exists("/.dockerenv"):
        return None
    try:
        return c.containers.get(socket.gethostname())
    except (NotFound, APIError):
        return None


def network_name(c: docker.DockerClient) -> str | None:
    """The network the PACS join: the lab's own (the re_ddns one), so apps reach them by name."""
    own = own_container(c)
    if own is not None:
        names = list(own.attrs["NetworkSettings"]["Networks"])
        return next((n for n in names if "ddns" in n), names[0] if names else None)
    try:
        c.networks.get(RE_DDNS_NETWORK)
        return RE_DDNS_NETWORK
    except (NotFound, APIError):
        return None


def explorer_where(c: docker.DockerClient) -> str:
    """Where DICOM Data Explorer runs: in the App Store if its container exists."""
    try:
        c.containers.get(EXPLORER_CONTAINER)
        return APPSTORE
    except (NotFound, APIError):
        return MAC


# -- reading the PACS back from Docker ------------------------------------------------

def _env(container) -> dict[str, str]:
    return dict(item.split("=", 1) for item in container.attrs["Config"].get("Env") or [] if "=" in item)


def _from_container(container) -> LabPacs | None:
    labels = container.labels or {}
    kind = labels.get(LABEL_KIND, "")
    if kind not in KINDS:
        return None
    return LabPacs(
        name=container.name,
        label=labels.get(f"{PREFIX}.label", container.name),
        kind=kind,
        aet=labels.get(f"{PREFIX}.aet", ""),
        dicom_port=int(labels.get(f"{PREFIX}.dicom-port", "0") or 0),
        http_port=int(labels.get(f"{PREFIX}.http-port", "0") or 0),
        password=_env(container).get("ORTHANC_PASSWORD", ""),
        explorer_at=labels.get(f"{PREFIX}.explorer-at", APPSTORE),
        status=container.status,
        created=labels.get(f"{PREFIX}.created", ""),
    )


def list_pacs(c: docker.DockerClient) -> list[LabPacs]:
    found = [_from_container(x) for x in c.containers.list(all=True, filters={"label": LABEL_KIND})]
    return sorted((p for p in found if p), key=lambda p: p.created)


def get_pacs(c: docker.DockerClient, name: str) -> LabPacs | None:
    try:
        return _from_container(c.containers.get(name))
    except (NotFound, APIError):
        return None


def next_number(c: docker.DockerClient, kind: str) -> int:
    taken = {p.aet for p in list_pacs(c)}
    n = 1
    while f"{KINDS[kind].aet_prefix}_{n}" in taken:
        n += 1
    return n


def reach(c: docker.DockerClient, p: LabPacs) -> tuple[str, int, int]:
    """(host, web port, DICOM port) the lab itself uses to talk to a PACS."""
    own = own_container(c)
    if own is not None:  # on the same Docker network: by name, container ports
        spec = KINDS[p.kind]
        return p.name, spec.http_port, spec.dicom_port
    return "localhost", p.http_port, p.dicom_port


# -- images -----------------------------------------------------------------------------

def ensure_image(c: docker.DockerClient, kind: str, progress: Progress) -> None:
    image = KINDS[kind].image
    try:
        c.images.get(image)
        return
    except ImageNotFound:
        pass
    if image == MINI_IMAGE:
        _build_mini(c, progress)
        return
    repo, _, tag = image.rpartition(":")
    layers: dict[str, tuple[int, int]] = {}
    for event in c.api.pull(repo, tag=tag, stream=True, decode=True):
        detail = event.get("progressDetail") or {}
        if event.get("id") and detail.get("total"):
            layers[event["id"]] = (detail.get("current", 0), detail["total"])
        done = sum(cur for cur, _ in layers.values())
        total = sum(tot for _, tot in layers.values())
        if total:
            progress(f"{done / 1e6:.0f} / {total / 1e6:.0f} MB")


def _build_mini(c: docker.DockerClient, progress: Progress) -> None:
    """A small image: python + pynetdicom + mini_pacs.py (from the PACS lab of DICOM Data Explorer)."""
    script = resources.files("pacs_lab.services").joinpath("mini_pacs.py").read_bytes()
    dockerfile = (
        "FROM python:3.11-slim\n"
        "ARG PIP_INDEX_URL=\nARG PIP_TRUSTED_HOST=\n"
        "RUN pip install --no-cache-dir pynetdicom==3.0.4 pydicom==3.0.2\n"
        "COPY mini_pacs.py /app/mini_pacs.py\n"
        'ENTRYPOINT ["python", "-u", "/app/mini_pacs.py"]\n'
    ).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in (("Dockerfile", dockerfile), ("mini_pacs.py", script)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    net = network_name(c)
    args = {"PIP_INDEX_URL": f"{PKG_CACHE}/pypi/simple/", "PIP_TRUSTED_HOST": "pkg-cache"} if _has_pkg_cache(c) else {}
    for event in c.api.build(
        fileobj=buf, custom_context=True, tag=MINI_IMAGE, rm=True, decode=True,
        buildargs=args, network_mode=net if args else None,
    ):
        if "error" in event:
            raise LabError("build_failed:" + str(event["error"]).strip())
        line = str(event.get("stream", "")).strip()
        if line.startswith("Step"):
            progress(line.split(":", 1)[0])


def _has_pkg_cache(c: docker.DockerClient) -> bool:
    try:
        return c.containers.get("pkg-cache").status == "running"
    except (NotFound, APIError):
        return False


# -- containers -------------------------------------------------------------------------

def _host_ports_in_use(c: docker.DockerClient) -> set[int]:
    used: set[int] = set()
    for container in c.containers.list(all=True):
        for bindings in (container.attrs.get("HostConfig", {}).get("PortBindings") or {}).values():
            for b in bindings or []:
                if str(b.get("HostPort", "")).isdigit():
                    used.add(int(b["HostPort"]))
    return used


def _free_port(start: int, used: set[int]) -> int:
    port = start
    while port in used or not _port_free_here(port):
        port += 1
    return port


def _port_free_here(port: int) -> bool:
    """On a Mac (not in a container) also skip ports another program listens on."""
    if os.path.exists("/.dockerenv"):
        return True
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def run_pacs(
    c: docker.DockerClient, *, kind: str, name: str, label: str, aet: str, password: str, explorer_at: str,
    created: str = "", host_ports: tuple[int, int] | None = None,
) -> LabPacs:
    """Create and start the container; its data lives in the volume <name>-data."""
    spec = KINDS[kind]
    used = _host_ports_in_use(c)
    for _attempt in range(10):
        if host_ports:
            dicom_host, http_host = host_ports
        else:
            dicom_host = _free_port(HOST_PORT_BASE[spec.dicom_port], used)
            http_host = _free_port(HOST_PORT_BASE[spec.http_port], used | {dicom_host}) if spec.http_port else 0
        ports = {f"{spec.dicom_port}/tcp": ("127.0.0.1", dicom_host)}
        if spec.http_port:
            ports[f"{spec.http_port}/tcp"] = ("127.0.0.1", http_host)
        labels = {
            LABEL_KIND: kind, f"{PREFIX}.label": label, f"{PREFIX}.aet": aet,
            f"{PREFIX}.dicom-port": str(dicom_host), f"{PREFIX}.http-port": str(http_host),
            f"{PREFIX}.explorer-at": explorer_at,
            f"{PREFIX}.created": created or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        container = c.containers.create(
            spec.image,
            name=name,
            hostname=name,
            command=container_command(kind, aet=aet, explorer_at=explorer_at),
            environment=container_env(kind, aet=aet, label=label, password=password, explorer_at=explorer_at),
            labels=labels,
            ports=ports,
            volumes={f"{name}-data": {"bind": spec.data_path, "mode": "rw"}},
            mem_limit=spec.memory,
            restart_policy={"Name": "unless-stopped"},
            network=network_name(c),
        )
        try:
            container.start()
        except APIError as exc:
            container.remove(force=True)
            text = str(exc).lower()
            clash = any(t in text for t in ("port is already allocated", "address already in use", "ports are not available"))
            if host_ports or not clash:
                raise LabError("start_failed:" + str(exc.explanation or exc)) from exc
            used |= {dicom_host, http_host}
            continue
        container.reload()
        return _from_container(container)
    raise LabError("no_free_port")


def recreate(c: docker.DockerClient, name: str, *, explorer_at: str) -> LabPacs:
    """Start the same PACS again with another C-MOVE destination; its data volume stays."""
    p = get_pacs(c, name)
    if p is None:
        raise LabError("not_found")
    c.containers.get(name).remove(force=True)
    return run_pacs(
        c, kind=p.kind, name=p.name, label=p.label, aet=p.aet, password=p.password,
        explorer_at=explorer_at, created=p.created, host_ports=(p.dicom_port, p.http_port),
    )


def start(c: docker.DockerClient, name: str) -> None:
    c.containers.get(name).start()


def stop(c: docker.DockerClient, name: str) -> None:
    c.containers.get(name).stop(timeout=10)


def remove(c: docker.DockerClient, name: str) -> None:
    """The container and its data volume."""
    try:
        c.containers.get(name).remove(force=True)
    except NotFound:
        pass
    try:
        c.volumes.get(f"{name}-data").remove(force=True)
    except NotFound:
        pass


def logs(c: docker.DockerClient, name: str, lines: int = 120) -> str:
    raw = c.containers.get(name).logs(tail=lines, timestamps=False)
    return raw.decode("utf-8", errors="replace")


def wait_running(c: docker.DockerClient, name: str, seconds: float = 20) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        container = c.containers.get(name)
        if container.status == "running":
            return
        if container.status in ("exited", "dead"):
            raise LabError("exited:" + logs(c, name, 15))
        time.sleep(0.5)
    raise LabError("not_running")
