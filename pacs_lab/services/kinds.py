"""The practice PACS this lab can start, and what DICOM Data Explorer needs to use them.

Each PACS is one Docker container. Everything the lab needs to know about it
later is written on the container itself (labels, and the Orthanc password in
its environment), so the list never drifts from what Docker really runs.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re

ORTHANC_IMAGE = "orthancteam/orthanc:26.9.1"  # Orthanc 1.13.0, checked with DICOM Data Explorer
MINI_IMAGE = "pacs-lab/mini-pacs:1"

# DICOM Data Explorer's C-MOVE receiver (its services/pacs_config.py defaults).
EXPLORER_AET = "DDE_EXPLORER"
EXPLORER_PORT = 11120
EXPLORER_CONTAINER = "smart-app-dicom-data-explorer"  # its App Store container

APPSTORE, MAC = "appstore", "mac"  # where DICOM Data Explorer runs


@dataclasses.dataclass(frozen=True)
class Kind:
    id: str
    image: str
    dicom_port: int  # inside the container
    http_port: int  # inside the container; 0: no web page and no DICOMweb
    retrieve: str  # what DICOM Data Explorer should retrieve with
    memory: str
    data_path: str  # where the PACS keeps its files (a Docker volume)
    aet_prefix: str
    label_prefix: str


KINDS = {
    "orthanc": Kind("orthanc", ORTHANC_IMAGE, 4242, 8042, "C-GET", "512m", "/var/lib/orthanc/db", "ORTHANC", "Orthanc"),
    "orthanc-strict": Kind(
        "orthanc-strict", ORTHANC_IMAGE, 4242, 8042, "C-MOVE", "512m", "/var/lib/orthanc/db", "STRICT", "Strict Orthanc"
    ),
    "mini": Kind("mini", MINI_IMAGE, 11112, 0, "C-GET", "256m", "/data", "MINI", "Mini PACS"),
}

# Ports on this computer: the first PACS of a kind gets these, the next ones count up.
HOST_PORT_BASE = {4242: 4242, 8042: 8042, 11112: 11112}


@dataclasses.dataclass
class LabPacs:
    """One practice PACS, as read back from its container."""

    name: str  # container name, also its name on the Docker network
    label: str
    kind: str
    aet: str
    dicom_port: int  # on this computer
    http_port: int = 0  # on this computer; 0 without a web page
    password: str = ""
    explorer_at: str = APPSTORE
    status: str = ""  # Docker's: running, exited, restarting, created...
    created: str = ""

    @property
    def spec(self) -> Kind:
        return KINDS[self.kind]

    @property
    def web_page(self) -> str:
        """Orthanc Explorer 2, opened in a browser on this computer."""
        return f"http://localhost:{self.http_port}/ui/app/" if self.http_port else ""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "pacs"


def aet_for(kind: str, number: int) -> str:
    """An AE title: capitals, digits and _, at most 16 characters."""
    return f"{KINDS[kind].aet_prefix}_{number}"[:16]


def explorer_destination(explorer_at: str) -> tuple[str, int]:
    """Where the PACS sends C-MOVE images: DICOM Data Explorer's receiver."""
    if explorer_at == APPSTORE:
        return EXPLORER_CONTAINER, EXPLORER_PORT  # container to container on the re_ddns network
    # Docker Desktop's name for this computer. While the App Store's explorer holds port
    # 11120 here, one started with reflex run needs another (its DICOM_RECEIVER_PORT).
    return "host.docker.internal", int(os.environ.get("PACS_LAB_MAC_RECEIVER_PORT") or EXPLORER_PORT)


def container_env(kind: str, *, aet: str, label: str, password: str, explorer_at: str) -> dict[str, str]:
    """The orthancteam/orthanc settings: ORTHANC__X_Y is the configuration option XY."""
    if kind not in ("orthanc", "orthanc-strict"):
        return {}
    host, port = explorer_destination(explorer_at)
    explorer = {"AET": EXPLORER_AET, "Host": host, "Port": port}
    env = {
        "ORTHANC_PASSWORD": password,  # login "orthanc" for the web page and DICOMweb
        "ORTHANC__NAME": label,
        "ORTHANC__DICOM_AET": aet,
        "DICOM_WEB_PLUGIN_ENABLED": "true",
        "STONE_WEB_VIEWER_PLUGIN_ENABLED": "true",  # look at the images in its web page
    }
    if kind == "orthanc-strict":
        # Like many hospital PACS: only known AE titles, no C-GET, few answers.
        explorer["AllowGet"] = False
        env.update(
            {
                "ORTHANC__DICOM_CHECK_CALLED_AET": "true",
                "ORTHANC__STRICT_AET_COMPARISON": "true",
                "ORTHANC__DICOM_ALWAYS_ALLOW_ECHO": "false",
                "ORTHANC__DICOM_ALWAYS_ALLOW_STORE": "false",
                "ORTHANC__LIMIT_FIND_RESULTS": "50",
            }
        )
    env["ORTHANC__DICOM_MODALITIES"] = json.dumps({EXPLORER_AET: explorer})
    return env


def container_command(kind: str, *, aet: str, explorer_at: str) -> list[str] | None:
    if kind != "mini":
        return None
    host, port = explorer_destination(explorer_at)
    spec = KINDS[kind]
    return [
        "--aet", aet, "--port", str(spec.dicom_port), "--bind", "0.0.0.0",
        "--store", spec.data_path, "--dest", f"{EXPLORER_AET}={host}:{port}",
    ]


# -- what to type into DICOM Data Explorer's PACS form --------------------------------

@dataclasses.dataclass
class Field:
    label: str  # exactly as on DICOM Data Explorer's PACS form
    value: str
    hint: str = ""  # i18n key explaining it
    secret: bool = False


@dataclasses.dataclass
class Card:
    title: str  # i18n key
    fields: list[Field]


def explorer_cards(p: LabPacs) -> list[Card]:
    """One card per way DICOM Data Explorer can talk to this PACS, field by field."""
    spec = p.spec
    in_appstore = p.explorer_at == APPSTORE
    host = p.name if in_appstore else "127.0.0.1"
    cards = []
    if spec.http_port:
        url = f"http://{p.name}:{spec.http_port}/dicom-web" if in_appstore else f"http://localhost:{p.http_port}/dicom-web"
        cards.append(
            Card(
                "card_dicomweb",
                [
                    Field("Name", f"{p.label} (web)", "hint_name"),
                    Field("How the app talks to it", "DICOMweb (HTTP)", "hint_dicomweb"),
                    Field("DICOMweb address (QIDO-RS)", url, "hint_url"),
                    Field("Login", "User name and password", "hint_login"),
                    Field("User name", "orthanc", ""),
                    Field("Password", p.password, "", secret=True),
                ],
            )
        )
    retrieve = (
        "C-MOVE (the PACS sends them to our receiver)" if spec.retrieve == "C-MOVE"
        else "C-GET (images come back on our connection)"
    )
    cards.append(
        Card(
            "card_dimse",
            [
                Field("Name", p.label, "hint_name"),
                Field("How the app talks to it", "DIMSE (C-FIND, C-GET, C-MOVE)", "hint_dimse"),
                Field("Host or IP", host, "hint_host_appstore" if in_appstore else "hint_host_mac"),
                Field("Port", str(spec.dicom_port if in_appstore else p.dicom_port), "hint_port"),
                Field("The PACS's AE title", p.aet, "hint_called"),
                Field("Our AE title", EXPLORER_AET, "hint_calling"),
                Field("Retrieve with", retrieve, "hint_move" if spec.retrieve == "C-MOVE" else "hint_get"),
            ],
        )
    )
    return cards
