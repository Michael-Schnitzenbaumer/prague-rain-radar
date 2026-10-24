from __future__ import annotations

import hashlib
import math
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

INDEX_URL = (
    "https://opendata.chmi.cz/meteorology/weather/radar/"
    "composite/pseudocappi2km/hdf5/"
)
FILENAME_RE = re.compile(r"T_PANV23_C_OKPR_(\d{14})\.hdf")
USER_AGENT = "PragueRainRadar/1.0 (public archival research project)"
EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True, order=True)
class SourceFile:
    timestamp: datetime
    name: str

    @property
    def url(self) -> str:
        return INDEX_URL + self.name


@dataclass(frozen=True)
class Grid:
    west: float
    south: float
    east: float
    north: float
    xscale: float
    yscale: float
    width: int
    height: int


def fetch_bytes(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_index(html: str) -> list[SourceFile]:
    found: dict[str, SourceFile] = {}
    for match in FILENAME_RE.finditer(html):
        name = match.group(0)
        stamp = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
        found[name] = SourceFile(stamp, name)
    return sorted(found.values())


def quarter_hour_files(files: list[SourceFile], day: str) -> list[SourceFile]:
    return [
        item
        for item in files
        if item.timestamp.date().isoformat() == day
        and item.timestamp.minute % 15 == 0
        and item.timestamp.second == 0
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_radar(path: Path) -> tuple[np.ndarray, Grid, datetime]:
    with h5py.File(path, "r") as hdf:
        encoded = hdf["dataset1/data1/data"][...]
        attrs = hdf["dataset1/data1/what"].attrs
        gain = float(attrs["gain"])
        offset = float(attrs["offset"])
        nodata = int(attrs["nodata"])
        where = hdf["where"].attrs
        grid = Grid(
            west=float(where["LL_lon"]),
            south=float(where["LL_lat"]),
            east=float(where["UR_lon"]),
            north=float(where["UR_lat"]),
            xscale=float(where["xscale"]),
            yscale=float(where["yscale"]),
            width=int(where["xsize"]),
            height=int(where["ysize"]),
        )
        root = hdf["what"].attrs
        date = _text(root["date"])
        time = _text(root["time"])

    values = encoded.astype(np.float32) * gain + offset
    values[encoded == nodata] = np.nan
    stamp = datetime.strptime(date + time, "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc
    )
    return values, grid, stamp


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii")
    if hasattr(value, "decode"):
        return value.decode("ascii")
    return str(value)


def _mercator_x(lon: float) -> float:
    return EARTH_RADIUS_M * math.radians(lon)


def _mercator_y(lat: float) -> float:
    latitude = max(min(lat, 85.05112878), -85.05112878)
    return EARTH_RADIUS_M * math.log(
        math.tan(math.pi / 4.0 + math.radians(latitude) / 2.0)
    )


def crop_indices(
    grid: Grid, west: float, south: float, east: float, north: float
) -> tuple[int, int, int, int]:
    if not (grid.west <= west < east <= grid.east):
        raise ValueError("longitude bounds fall outside the CHMI grid")
    if not (grid.south <= south < north <= grid.north):
        raise ValueError("latitude bounds fall outside the CHMI grid")

    x0 = int(math.floor((_mercator_x(west) - _mercator_x(grid.west)) / grid.xscale))
    x1 = int(math.ceil((_mercator_x(east) - _mercator_x(grid.west)) / grid.xscale))
    y0 = int(math.floor((_mercator_y(grid.north) - _mercator_y(north)) / grid.yscale))
    y1 = int(math.ceil((_mercator_y(grid.north) - _mercator_y(south)) / grid.yscale))
    return (
        max(0, x0),
        max(0, y0),
        min(grid.width, x1),
        min(grid.height, y1),
    )


def crop_radar(
    values: np.ndarray,
    grid: Grid,
    west: float,
    south: float,
    east: float,
    north: float,
) -> np.ndarray:
    x0, y0, x1, y1 = crop_indices(grid, west, south, east, north)
    return values[y0:y1, x0:x1]

