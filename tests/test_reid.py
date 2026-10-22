"""New UIDs and made-up patients: a SEG must still point at its CT."""

from __future__ import annotations

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian

from pacs_lab.services import reid

CT_SERIES, SEG_SERIES, STUDY, FOR = "1.2.3.10", "1.2.3.20", "1.2.3", "1.2.3.99"


def image(sop: str, series: str, modality: str, patient: str = "REAL-1", sex: str = "F") -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.SOPInstanceUID, ds.SeriesInstanceUID, ds.StudyInstanceUID = sop, series, STUDY
    ds.FrameOfReferenceUID = FOR
    ds.PatientID, ds.PatientName, ds.PatientSex = patient, "REAL^NAME", sex
    ds.Modality, ds.StudyDescription, ds.AccessionNumber = modality, "Chest", "REAL-ACC"
    return ds


def seg_of(cts: list[Dataset]) -> Dataset:
    seg = image("1.2.3.20.1", SEG_SERIES, "SEG")
    ref_series = Dataset()
    ref_series.SeriesInstanceUID = CT_SERIES
    ref_series.ReferencedInstanceSequence = Sequence([_ref(ct.SOPInstanceUID) for ct in cts])
    seg.ReferencedSeriesSequence = Sequence([ref_series])
    seg.OtherPatientIDs = "SECRET"
    return seg


def _ref(sop: str) -> Dataset:
    ds = Dataset()
    ds.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.ReferencedSOPInstanceUID = sop
    return ds


def test_a_seg_keeps_pointing_at_its_relabelled_ct():
    cts = [image(f"1.2.3.10.{n}", CT_SERIES, "CT") for n in (1, 2)]
    seg = seg_of(cts)
    relabel = reid.Relabel()
    for ds in (*cts, seg):
        relabel.learn(ds)
    new_cts = [relabel.apply(ds) for ds in cts]
    new_seg = relabel.apply(seg)

    ref = new_seg.ReferencedSeriesSequence[0]
    assert ref.SeriesInstanceUID == new_cts[0].SeriesInstanceUID != CT_SERIES
    assert [r.ReferencedSOPInstanceUID for r in ref.ReferencedInstanceSequence] == [ct.SOPInstanceUID for ct in new_cts]
    assert ref.ReferencedInstanceSequence[0].ReferencedSOPClassUID == "1.2.840.10008.5.1.4.1.1.2"  # classes stay
    assert new_seg.StudyInstanceUID == new_cts[0].StudyInstanceUID != STUDY
    assert new_seg.FrameOfReferenceUID == new_cts[1].FrameOfReferenceUID != FOR
    assert new_cts[0].file_meta.MediaStorageSOPInstanceUID == new_cts[0].SOPInstanceUID
    assert "OtherPatientIDs" not in new_seg
    assert {ds.PatientID for ds in (*new_cts, new_seg)} == {"LAB00001"}
    assert new_seg.PatientName == "CHEN^MEILING"  # PatientSex F
    assert new_seg.AccessionNumber == new_cts[0].AccessionNumber != "REAL-ACC"


def test_the_patient_book_gives_the_same_made_up_patient_every_time():
    book: dict[str, dict] = {}
    first = reid.Relabel(book=book)
    first.learn(image("1.1", "2.2", "CT", patient="REAL-1", sex="M"))
    first.learn(image("1.3", "2.4", "CT", patient="REAL-2", sex="M"))
    assert [p["id"] for p in first.patients.values()] == ["LAB00001", "LAB00002"]

    again = reid.Relabel(book=book, first_number=first.next_number)
    again.learn(image("1.1", "2.2", "CT", patient="REAL-1", sex="M"))
    again.learn(image("1.9", "2.9", "MR", patient="REAL-3", sex="F"))
    assert again.patients["REAL-1"]["id"] == "LAB00001"
    assert again.patients["REAL-1"]["name"] == first.patients["REAL-1"]["name"]
    assert again.patients["REAL-3"]["id"] == "LAB00003"
    assert again.uids["1.1"] != first.uids["1.1"]  # each copy gets its own UIDs


def test_relabelled_files_round_trip_as_dicom():
    from io import BytesIO

    from pydicom import dcmread

    ct = image("1.2.3.10.1", CT_SERIES, "CT")
    relabel = reid.Relabel()
    relabel.learn(ct)
    data = reid.to_bytes(relabel.apply(ct))
    back = dcmread(BytesIO(data))
    assert data[128:132] == b"DICM"
    assert back.PatientID == "LAB00001" and back.SOPInstanceUID != "1.2.3.10.1"
