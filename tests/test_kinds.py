"""What each practice PACS is told, and what DICOM Data Explorer is told to type."""

from __future__ import annotations

import json

import pytest

from pacs_lab.i18n import TEXTS, error_text
from pacs_lab.services import kinds
from pacs_lab.services.kinds import LabPacs


def test_the_easy_orthanc_knows_the_explorer_and_allows_everything():
    env = kinds.container_env("orthanc", aet="ORTHANC_1", label="Orthanc 1", password="pw", explorer_at=kinds.APPSTORE)
    assert env["ORTHANC__DICOM_AET"] == "ORTHANC_1" and env["ORTHANC_PASSWORD"] == "pw"
    assert json.loads(env["ORTHANC__DICOM_MODALITIES"]) == {
        "DDE_EXPLORER": {"AET": "DDE_EXPLORER", "Host": "smart-app-dicom-data-explorer", "Port": 11120}
    }
    assert "ORTHANC__DICOM_CHECK_CALLED_AET" not in env


def test_the_strict_orthanc_refuses_c_get_and_unknown_ae_titles():
    env = kinds.container_env("orthanc-strict", aet="STRICT_1", label="S", password="pw", explorer_at=kinds.MAC)
    explorer = json.loads(env["ORTHANC__DICOM_MODALITIES"])["DDE_EXPLORER"]
    assert explorer == {"AET": "DDE_EXPLORER", "Host": "host.docker.internal", "Port": 11120, "AllowGet": False}
    assert env["ORTHANC__DICOM_CHECK_CALLED_AET"] == "true" and env["ORTHANC__LIMIT_FIND_RESULTS"] == "50"


def test_the_mini_pacs_is_started_with_its_move_destination():
    cmd = kinds.container_command("mini", aet="MINI_1", explorer_at=kinds.APPSTORE)
    assert cmd[cmd.index("--dest") + 1] == "DDE_EXPLORER=smart-app-dicom-data-explorer:11120"
    assert kinds.container_env("mini", aet="MINI_1", label="M", password="", explorer_at=kinds.MAC) == {}


def _fields(cards):
    return [{f.label: f.value for f in card.fields} for card in cards]


def test_settings_for_an_explorer_in_the_app_store_use_the_container_name():
    p = LabPacs("pacs-lab-orthanc-1", "Orthanc 1", "orthanc", "ORTHANC_1", 4250, 8050, "pw", kinds.APPSTORE)
    web, dimse = _fields(kinds.explorer_cards(p))
    assert web["DICOMweb address (QIDO-RS)"] == "http://pacs-lab-orthanc-1:8042/dicom-web"
    assert web["Password"] == "pw" and web["Login"] == "User name and password"
    assert (dimse["Host or IP"], dimse["Port"], dimse["The PACS's AE title"]) == ("pacs-lab-orthanc-1", "4242", "ORTHANC_1")
    assert dimse["Retrieve with"].startswith("C-GET")


def test_settings_for_an_explorer_on_this_computer_use_the_published_ports():
    p = LabPacs("pacs-lab-orthanc-strict-1", "Strict 1", "orthanc-strict", "STRICT_1", 4243, 8043, "pw", kinds.MAC)
    web, dimse = _fields(kinds.explorer_cards(p))
    assert web["DICOMweb address (QIDO-RS)"] == "http://localhost:8043/dicom-web"
    assert (dimse["Host or IP"], dimse["Port"]) == ("127.0.0.1", "4243")
    assert dimse["Retrieve with"].startswith("C-MOVE")


def test_the_mini_pacs_has_no_dicomweb_card():
    p = LabPacs("pacs-lab-mini-1", "Mini 1", "mini", "MINI_1", 11112, 0, "", kinds.MAC)
    (dimse,) = _fields(kinds.explorer_cards(p))
    assert dimse["Port"] == "11112" and p.web_page == ""


def test_ae_titles_fit_in_16_characters():
    assert kinds.aet_for("orthanc-strict", 12345678) == "STRICT_12345678"[:16]
    assert all(len(kinds.aet_for(k, 99)) <= 16 for k in kinds.KINDS)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_errors_are_told_in_words(lang):
    assert error_text(lang, "no_docker") == TEXTS[lang]["err_no_docker"]
    assert "boom" in error_text(lang, "start_failed:boom")
    assert "weird" in error_text(lang, "weird")  # unknown keys still show what happened
    assert set(TEXTS["zh"]) == set(TEXTS["en"])  # both languages have every text
