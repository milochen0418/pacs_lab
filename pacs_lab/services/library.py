"""Series in the shared DICOM folder (the "dicom" collection), e.g. what DICOM Data Explorer downloaded."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from reflex_ddns_auth.collections import Collection

KIND = "dicom.series"


@dataclasses.dataclass
class LibrarySeries:
    uid: str
    owner: str
    modality: str
    description: str
    collection: str
    images: int
    mb: float


def _dicom() -> Collection:
    return Collection("dicom", app_id="pacs-lab")


def list_series() -> list[LibrarySeries]:
    found = []
    for item in _dicom().local_items(kind=KIND):
        if item.path is None:
            continue
        meta = item.meta or {}
        found.append(
            LibrarySeries(
                uid=item.id,
                owner=item.owner,
                modality=str(meta.get("Modality") or ""),
                description=str(meta.get("SeriesDescription") or item.title or ""),
                collection=str(meta.get("Collection") or ""),
                images=int(meta.get("ImageCount") or len(item.files)),
                mb=round(item.bytes / 1e6, 1),
            )
        )
    found.sort(key=lambda s: (s.collection, s.modality, s.description))
    return found


def files_of(uids: list[str]) -> dict[str, list[Path]]:
    wanted = set(uids)
    found: dict[str, list[Path]] = {}
    for item in _dicom().local_items(kind=KIND):
        if item.id in wanted and item.path is not None:
            found[item.id] = sorted(item.path / f["path"] for f in item.files)
    return found
