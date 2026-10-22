"""New identities for copied series: new UIDs and a made-up patient.

A PACS keeps one copy per UID, and DICOM Data Explorer skips series it has
already downloaded, so copies of known series get new Study/Series/SOP
Instance UIDs. Every UID is mapped the same way across one batch, so a SEG
still points at its CT. Each real patient becomes a made-up one (name, ID)
from the lab's patient book, the same one in every practice PACS, and each
study gets an accession number, to practise searching with.
"""

from __future__ import annotations

import io
import random

from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

_MAPPED_KEYWORDS = ("StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "FrameOfReferenceUID")

NAMES = {
    "F": ["CHEN^MEILING", "HUANG^YATING", "LI^JIAHUI", "LIU^SHUFEN", "YANG^PEIYU", "ZHENG^YUTING", "LIN^XINYI"],
    "M": ["WANG^XIAOMING", "LIN^ZHIHAO", "ZHANG^WEI", "WU^CHENGEN", "CAI^ZONGHAN", "XU^JUNJIE", "HUANG^GUANYU"],
}


class Relabel:
    """learn() every file of a batch first (headers are enough), then apply() to each."""

    def __init__(self, book: dict[str, dict] | None = None, first_number: int = 1, rng: random.Random | None = None):
        self.next_number = first_number
        self.book = book if book is not None else {}  # real PatientID -> made-up patient, kept by the lab
        self.uids: dict[str, str] = {}
        self.patients: dict[str, dict] = {}  # this batch's patients
        self.accessions: dict[str, str] = {}  # real StudyInstanceUID -> accession number
        self._rng = rng or random.Random()

    def learn(self, ds: Dataset) -> None:
        for keyword in _MAPPED_KEYWORDS:
            value = str(ds.get(keyword, "") or "")
            if value and value not in self.uids:
                self.uids[value] = generate_uid()
        real = str(ds.get("PatientID", "") or ds.get("PatientName", "") or "?")
        if real not in self.book:
            sex = str(ds.get("PatientSex", "") or "")
            names = NAMES.get(sex) or NAMES["F" if self.next_number % 2 else "M"]
            used = {p["name"] for p in self.book.values()}
            name = next((n for n in names if n not in used), f"{names[0]}{self.next_number}")
            self.book[real] = {"id": f"LAB{self.next_number:05d}", "name": name}
            self.next_number += 1
        if real not in self.patients:
            self.patients[real] = {**self.book[real], "real": real, "studies": []}
        study = str(ds.get("StudyInstanceUID", "") or "")
        if study and study not in self.accessions:
            self.accessions[study] = f"A{self._rng.randrange(10**6):06d}"
            self.patients[real]["studies"].append(str(ds.get("StudyDescription", "") or ""))

    def apply(self, ds: Dataset) -> Dataset:
        real = str(ds.get("PatientID", "") or ds.get("PatientName", "") or "?")
        study = str(ds.get("StudyInstanceUID", "") or "")
        uids = self.uids

        def remap(dataset: Dataset, elem) -> None:
            if elem.VR != "UI" or elem.value is None:
                return
            if isinstance(elem.value, str):
                elem.value = uids.get(elem.value, elem.value)
            else:
                elem.value = [uids.get(v, v) for v in elem.value]

        ds.walk(remap)
        if getattr(ds, "file_meta", None) is not None and "MediaStorageSOPInstanceUID" in ds.file_meta:
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        patient = self.patients.get(real)
        if patient:
            ds.PatientID, ds.PatientName = patient["id"], patient["name"]
        if study in self.accessions:
            ds.AccessionNumber = self.accessions[study]
        for keyword in ("OtherPatientIDsSequence", "OtherPatientIDs", "OtherPatientNames"):
            if keyword in ds:
                delattr(ds, keyword)
        return ds


def to_bytes(ds: Dataset) -> bytes:
    """The dataset as a DICOM file, in its own transfer syntax."""
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()
