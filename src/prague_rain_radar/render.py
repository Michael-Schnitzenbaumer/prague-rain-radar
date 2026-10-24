from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .chmi import crop_radar, read_radar

PRAGUE = (14.4378, 50.0755)
ATTRIBUTION = "Datenquelle: CHMI, CC BY 4.0"
COLOR_STOPS = [
    (-32.0, (18, 22, 28)),
    (0.0, (18, 22, 28)),
    (5.0, (55, 80, 110)),
    (10.0, (55, 145, 210)),
    (15.0, (50, 205, 235)),
    (20.0, (70, 210, 120)),
    (25.0, (155, 225, 70)),
    (30.0, (245, 225, 55)),
    (35.0, (250, 155, 40)),
    (40.0, (235, 70, 45)),
    (45.0, (205, 45, 105)),
    (50.0, (175, 65, 185)),
    (55.0, (235, 235, 245)),
]


def colorize(values: np.ndarray) -> np.ndarray:
    result = np.empty(values.shape + (3,), dtype=np.uint8)
    result[:] = COLOR_STOPS[0][1]
    finite = np.isfinite(values)
    for threshold, color in COLOR_STOPS[1:]:
        result[finite & (values >= threshold)] = color
    result[~finite] = (50, 50, 50)
    return result


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default()


def render_frame(
    hdf_path: Path,
    destination: Path,
    bounds: tuple[float, float, float, float],
    size: tuple[int, int] = (1280, 720),
) -> datetime:
    west, south, east, north = bounds
    values, grid, stamp = read_radar(hdf_path)
    cropped = crop_radar(values, grid, west, south, east, north)
    radar = Image.fromarray(colorize(cropped))

    width, height = size
    map_box = (55, 105, width - 55, height - 85)
    map_w = map_box[2] - map_box[0]
    map_h = map_box[3] - map_box[1]
    scale = min(map_w / radar.width, map_h / radar.height)
    radar = radar.resize(
        (max(1, int(radar.width * scale)), max(1, int(radar.height * scale))),
        Image.Resampling.NEAREST,
    )
    canvas = Image.new("RGB", size, (12, 16, 22))
    x = map_box[0] + (map_w - radar.width) // 2
    y = map_box[1] + (map_h - radar.height) // 2
    canvas.paste(radar, (x, y))
    draw = ImageDraw.Draw(canvas)

    title = _font(30, bold=True)
    body = _font(22)
    small = _font(17)
    tiny = _font(14)
    local = stamp.astimezone(ZoneInfo("Europe/Prague"))
    draw.text((55, 24), "Prague Rain Radar", fill=(245, 248, 252), font=title)
    draw.text(
        (55, 64),
        f"{local:%d.%m.%Y %H:%M} {local.tzname()}  |  {stamp:%Y-%m-%d %H:%M} UTC",
        fill=(205, 215, 226),
        font=body,
    )

    def point(lon: float, lat: float) -> tuple[int, int]:
        px = x + int((lon - west) / (east - west) * radar.width)
        py = y + int((north - lat) / (north - south) * radar.height)
        return px, py

    px, py = point(*PRAGUE)
    draw.ellipse((px - 7, py - 7, px + 7, py + 7), outline="white", width=3)
    draw.text((px + 12, py - 13), "Praha", fill="white", font=small, stroke_width=2, stroke_fill=(0, 0, 0))
    draw.text((x + 14, y + 12), "ZAPAD / WEST", fill="white", font=small, stroke_width=2, stroke_fill=(0, 0, 0))
    east_label = "VYCHOD / EAST"
    bbox = draw.textbbox((0, 0), east_label, font=small)
    draw.text((x + radar.width - (bbox[2] - bbox[0]) - 14, y + 12), east_label, fill="white", font=small, stroke_width=2, stroke_fill=(0, 0, 0))

    legend_y = height - 62
    legend_x = 55
    segment = 55
    for index, (threshold, color) in enumerate(COLOR_STOPS[2:]):
        left = legend_x + index * segment
        draw.rectangle((left, legend_y, left + segment, legend_y + 16), fill=color)
        draw.text((left, legend_y + 19), f"{threshold:g}", fill=(205, 215, 226), font=tiny)
    draw.text((legend_x + len(COLOR_STOPS[2:]) * segment + 10, legend_y - 2), "dBZ", fill=(205, 215, 226), font=small)
    attr_bbox = draw.textbbox((0, 0), ATTRIBUTION, font=tiny)
    draw.text((width - 55 - (attr_bbox[2] - attr_bbox[0]), height - 28), ATTRIBUTION, fill=(145, 155, 168), font=tiny)

    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=True)
    return stamp


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_video(
    input_dir: Path,
    month: str,
    output: Path,
    bounds: tuple[float, float, float, float],
    fps: int,
) -> dict[str, object]:
    sources: list[tuple[datetime, Path]] = []
    for path in input_dir.rglob("*.hdf"):
        _, _, stamp = read_radar(path)
        if stamp.strftime("%Y-%m") == month:
            sources.append((stamp, path))
    sources.sort()
    if not sources:
        raise RuntimeError(f"no HDF5 radar files found for {month}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prague-radar-frames-") as temp_name:
        frame_dir = Path(temp_name)
        for index, (_, path) in enumerate(sources):
            render_frame(path, frame_dir / f"{index:08d}.png", bounds)

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "%08d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        subprocess.run(command, check=True)
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(output), "-f", "null", "-"],
            check=True,
        )

    if output.stat().st_size < 1024:
        raise RuntimeError("rendered MP4 is unexpectedly small")
    result = {
        "schema": 1,
        "month": month,
        "frames": len(sources),
        "first_timestamp_utc": sources[0][0].isoformat().replace("+00:00", "Z"),
        "last_timestamp_utc": sources[-1][0].isoformat().replace("+00:00", "Z"),
        "fps": fps,
        "duration_seconds": len(sources) / fps,
        "bounds": {"west": bounds[0], "south": bounds[1], "east": bounds[2], "north": bounds[3]},
        "sha256": _sha256(output),
        "bytes": output.stat().st_size,
    }
    output.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a monthly Prague radar MP4")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--west", type=float, default=13.40)
    parser.add_argument("--south", type=float, default=49.60)
    parser.add_argument("--east", type=float, default=15.50)
    parser.add_argument("--north", type=float, default=50.50)
    parser.add_argument("--fps", type=int, default=24)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = render_video(
        args.input_dir,
        args.month,
        args.output,
        (args.west, args.south, args.east, args.north),
        args.fps,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

