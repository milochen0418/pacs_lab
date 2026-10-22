"""Checking a practice PACS the way DICOM Data Explorer will talk to it."""

from __future__ import annotations

import time

import requests
from pydicom.dataset import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind as FIND, Verification

from pacs_lab.services.kinds import EXPLORER_AET, KINDS, LabPacs

Result = tuple[str, str, dict]  # ("ok" | "fail", i18n key, params)


def _assoc(host: str, port: int, called: str, context):
    ae = AE(ae_title=EXPLORER_AET)  # the explorer's AE title: what the PACS must accept
    ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = 10
    ae.add_requested_context(context)
    return ae.associate(host, port, ae_title=called)


def echo(host: str, port: int, called: str) -> bool:
    assoc = _assoc(host, port, called, Verification)
    if not assoc.is_established:
        return False
    try:
        status = assoc.send_c_echo()
        return bool(status) and status.Status == 0x0000
    finally:
        assoc.release()


def count_studies(host: str, port: int, called: str) -> int | None:
    assoc = _assoc(host, port, called, FIND)
    if not assoc.is_established:
        return None
    query = Dataset()
    query.QueryRetrieveLevel = "STUDY"
    query.StudyInstanceUID = ""
    found = 0
    try:
        for status, ident in assoc.send_c_find(query, FIND):
            if status and status.Status in (0xFF00, 0xFF01) and ident is not None:
                found += 1
    finally:
        assoc.release()
    return found


def list_studies(host: str, port: int, called: str) -> list[dict]:
    """Every study, as a search from DICOM Data Explorer sees it."""
    assoc = _assoc(host, port, called, FIND)
    if not assoc.is_established:
        return []
    query = Dataset()
    query.QueryRetrieveLevel = "STUDY"
    for keyword in (
        "StudyInstanceUID", "PatientID", "PatientName", "StudyDate", "StudyDescription",
        "AccessionNumber", "ModalitiesInStudy", "NumberOfStudyRelatedInstances",
    ):
        setattr(query, keyword, "")
    found = []
    try:
        for status, ident in assoc.send_c_find(query, FIND):
            if not (status and status.Status in (0xFF00, 0xFF01) and ident is not None):
                continue
            modalities = ident.get("ModalitiesInStudy", "") or ""
            found.append(
                {
                    "patient_id": str(ident.get("PatientID", "") or ""),
                    "patient_name": str(ident.get("PatientName", "") or ""),
                    "date": str(ident.get("StudyDate", "") or ""),
                    "description": str(ident.get("StudyDescription", "") or ""),
                    "accession": str(ident.get("AccessionNumber", "") or ""),
                    "modalities": ", ".join(modalities) if not isinstance(modalities, str) else modalities,
                    "images": str(ident.get("NumberOfStudyRelatedInstances", "") or ""),
                }
            )
    finally:
        assoc.release()
    found.sort(key=lambda s: (s["patient_id"], s["date"]))
    return found


def web_ok(host: str, http_port: int, password: str) -> int | None:
    """Studies the DICOMweb search (QIDO-RS) returns, or None when it fails."""
    try:
        resp = requests.get(
            f"http://{host}:{http_port}/dicom-web/studies", auth=("orthanc", password), timeout=10,
            headers={"Accept": "application/dicom+json"},
        )
    except requests.RequestException:
        return None
    if resp.status_code == 204:
        return 0
    return len(resp.json()) if resp.status_code == 200 else None


def wait_ready(p: LabPacs, host: str, http_port: int, dicom_port: int, seconds: float = 120) -> bool:
    """Until the PACS answers: Orthanc's REST API, or C-ECHO for the mini PACS."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if KINDS[p.kind].http_port:
                resp = requests.get(f"http://{host}:{http_port}/system", auth=("orthanc", p.password), timeout=5)
                if resp.status_code == 200:
                    return True
            elif echo(host, dicom_port, p.aet):
                return True
        except (requests.RequestException, OSError):
            pass
        time.sleep(1)
    return False


def run(p: LabPacs, host: str, http_port: int, dicom_port: int) -> list[Result]:
    results: list[Result] = []
    spec = KINDS[p.kind]
    if spec.http_port:
        n = web_ok(host, http_port, p.password)
        results.append(("ok", "check_web_ok", {"n": n}) if n is not None else ("fail", "check_web_fail", {}))
    if echo(host, dicom_port, p.aet):
        results.append(("ok", "check_echo_ok", {"aet": p.aet}))
        n = count_studies(host, dicom_port, p.aet)
        results.append(("ok", "check_find_ok", {"n": n}) if n is not None else ("fail", "check_find_fail", {}))
    else:
        results.append(("fail", "check_echo_fail", {"aet": p.aet}))
    results.append(("note", "check_move_note" if spec.retrieve == "C-MOVE" else "check_get_note", {}))
    return results
