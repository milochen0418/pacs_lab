"""Putting files into a practice PACS: Orthanc's REST API, or C-STORE for the mini PACS.

Files are streamed: only a few are in memory at a time, whatever the series size.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

import requests
from pydicom.dataset import Dataset
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian
from pynetdicom import AE

from pacs_lab.services.docker_lab import LabError

LAB_AET = "PACS_LAB"
IN_FLIGHT = 8
Done = Callable[[int], None]  # files stored so far


def to_orthanc(base: str, password: str, blobs: Iterable[bytes], done: Done) -> int:
    """POST each file to <base>/instances (works on the strict Orthanc too: not DICOM)."""
    session = requests.Session()
    session.auth = ("orthanc", password)
    stored = 0
    lock = threading.Lock()
    slots = threading.Semaphore(IN_FLIGHT)

    def post(blob: bytes) -> None:
        nonlocal stored
        try:
            resp = session.post(
                f"{base}/instances", data=blob, headers={"Content-Type": "application/dicom"}, timeout=120
            )
            if resp.status_code >= 400:
                raise LabError(f"upload_failed:HTTP {resp.status_code} {resp.text[:200]}")
            with lock:
                stored += 1
                done(stored)
        finally:
            slots.release()

    with ThreadPoolExecutor(4) as pool:
        futures = []
        for blob in blobs:
            slots.acquire()
            futures.append(pool.submit(post, blob))
        for future in futures:
            future.result()
    return stored


def to_dimse(
    host: str, port: int, called_aet: str, contexts: dict[str, set[str]], datasets: Iterable[Dataset], done: Done
) -> int:
    """C-STORE every dataset as the AE title PACS_LAB; ``contexts`` = SOP class -> transfer syntaxes."""
    if len(contexts) > 120:
        raise LabError("too_many_kinds")
    ae = AE(ae_title=LAB_AET)
    for sop_class, syntaxes in contexts.items():
        ae.add_requested_context(sop_class, sorted(set(syntaxes) | {ExplicitVRLittleEndian, ImplicitVRLittleEndian}))
    assoc = ae.associate(host, port, ae_title=called_aet)
    if not assoc.is_established:
        raise LabError(f"store_refused:{called_aet}@{host}:{port}")
    stored = 0
    try:
        for ds in datasets:
            status = assoc.send_c_store(ds)
            if not status or status.Status not in (0x0000, 0xB000, 0xB006, 0xB007):
                code = f"0x{status.Status:04X}" if status else "no answer"
                raise LabError(f"store_failed:{code}")
            stored += 1
            done(stored)
    finally:
        assoc.release()
    return stored
