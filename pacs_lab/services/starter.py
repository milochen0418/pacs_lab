"""The starter set: three small public studies from IDC (NCI Imaging Data Commons).

Downloaded once over anonymous S3 into the lab's data folder, then reused for
every PACS. All CC BY: free to use with credit to the collections.
"""

from __future__ import annotations

import dataclasses
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlparse

import requests

from pacs_lab.services.paths import data_dir


@dataclasses.dataclass(frozen=True)
class StarterSeries:
    uid: str
    modality: str
    description: str
    images: int
    mb: float
    url: str  # s3://bucket/prefix/*


@dataclasses.dataclass(frozen=True)
class StarterStudy:
    key: str  # i18n: starter_<key>
    collection: str
    license: str
    series: tuple[StarterSeries, ...]

    @property
    def mb(self) -> float:
        return sum(s.mb for s in self.series)


STARTER = (
    StarterStudy(
        "kidney", "C4KC-KiTS (KiTS-00061)", "CC BY 3.0",
        (
            StarterSeries("1.3.6.1.4.1.14519.5.2.1.6919.4624.322088738018313179675994057197", "CT", "arterial", 29, 15.34,
                          "s3://idc-open-data/55e38cd7-a2d5-4088-aa03-9795de23925b/*"),
            StarterSeries("1.2.276.0.7230010.3.1.3.0.75019.1588584314.382026", "SEG", "Segmentation", 1, 1.94,
                          "s3://idc-open-data/0ef0c911-826e-4670-ba72-dbda914567fa/*"),
        ),
    ),
    StarterStudy(
        "lung", "NLST (107610) + NLSTSeg", "CC BY 4.0",
        (
            StarterSeries("1.2.840.113654.2.55.262564043997006039201662725545109911310", "CT",
                          "0,OPA,SE,SEN16,B30f,276,2,120,45,30,na", 162, 85.29,
                          "s3://idc-open-data/ce0b3c39-4b3e-474f-a6bf-70a90458ac6a/*"),
            StarterSeries("1.2.276.0.7230010.3.1.3.481037312.100731.1761242635.594453", "SEG",
                          "NLSTSeg Segmentation of Series: 4", 1, 0.17,
                          "s3://idc-open-data/5470b4dd-7e6a-4b8c-8d21-6984576f1476/*"),
        ),
    ),
    StarterStudy(
        "xray", "COVID-19-AR (COVID-19-AR-16434356)", "CC BY 4.0",
        (
            StarterSeries("1.3.6.1.4.1.14519.5.2.1.9999.103.3144050301958868320974875419705", "CR", "XR CHEST AP PORTABLE",
                          1, 5.64, "s3://idc-open-data/7efc4433-cd5b-459d-9c3b-5234c9fbdcad/*"),
        ),
    ),
)

Progress = Callable[[int, int], None]  # (bytes done, bytes total)


def _bucket_prefix(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    return parsed.netloc, parsed.path.lstrip("/").replace("*", "")


def _list(session: requests.Session, bucket: str, prefix: str) -> list[tuple[str, int]]:
    """Every file under the prefix with its size (S3 ListObjectsV2, anonymous)."""
    found, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        resp = session.get(f"https://{bucket}.s3.amazonaws.com", params=params, timeout=(10, 60))
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for node in root.findall("{*}Contents"):
            key = node.findtext("{*}Key") or ""
            if key and not key.endswith("/"):
                found.append((key, int(node.findtext("{*}Size") or 0)))
        token = root.findtext("{*}NextContinuationToken")
        if not token:
            return found


def cache_dir(series_uid: str) -> Path:
    return data_dir() / "starter" / series_uid


def is_cached(series_uid: str) -> bool:
    return (cache_dir(series_uid) / ".complete").is_file()


def download(studies: list[StarterStudy], progress: Progress) -> dict[str, list[Path]]:
    """The files of every series, from the cache or IDC: {series UID: [paths]}."""
    session = requests.Session()
    plan: list[tuple[StarterSeries, str, str, int]] = []
    for series in (s for study in studies for s in study.series):
        if is_cached(series.uid):
            continue
        bucket, prefix = _bucket_prefix(series.url)
        plan += [(series, bucket, key, size) for key, size in _list(session, bucket, prefix)]
    total = sum(size for *_, size in plan)
    done = 0
    lock = threading.Lock()
    progress(0, total)

    def fetch(item) -> None:
        nonlocal done
        series, bucket, key, _size = item
        folder = cache_dir(series.uid)
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / key.rsplit("/", 1)[-1]
        part = dest.with_suffix(dest.suffix + ".part")
        url = f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"
        with session.get(url, stream=True, timeout=(10, 120)) as resp:
            resp.raise_for_status()
            with part.open("wb") as fh:
                for chunk in resp.iter_content(256 * 1024):
                    fh.write(chunk)
                    with lock:
                        done += len(chunk)
                        progress(done, total)
        part.replace(dest)

    with ThreadPoolExecutor(6) as pool:
        list(pool.map(fetch, plan))
    for series in (s for study in studies for s in study.series):
        (cache_dir(series.uid) / ".complete").touch()
    return {
        s.uid: sorted(p for p in cache_dir(s.uid).iterdir() if p.is_file() and not p.name.startswith("."))
        for study in studies for s in study.series
    }
