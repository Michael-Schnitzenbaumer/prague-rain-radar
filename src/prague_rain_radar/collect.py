from __future__ import annotations

import argparse
import gzip
import io
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

import h5py

from .chmi import INDEX_URL, fetch_bytes, parse_index, quarter_hour_files, sha256_file


def _safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise ValueError(f"unsafe archive member: {member.name}")
        try:
            tar.extractall(destination, filter="data")
        except TypeError:  # Python 3.11 and older; members were validated above.
            tar.extractall(destination)


def _valid_hdf(path: Path) -> None:
    with h5py.File(path, "r") as hdf:
        data = hdf["dataset1/data1/data"]
        if data.ndim != 2 or data.size == 0:
            raise ValueError(f"unexpected radar grid in {path.name}")


def _write_deterministic_archive(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for path in sorted(source.rglob("*")):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(source).as_posix()
                    info = tar.gettarinfo(str(path), arcname=relative)
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    with path.open("rb") as handle:
                        tar.addfile(info, handle)


def collect_day(day: str, output: Path, existing: Path | None = None) -> dict[str, object]:
    html = fetch_bytes(INDEX_URL).decode("utf-8", errors="replace")
    candidates = quarter_hour_files(parse_index(html), day)

    with tempfile.TemporaryDirectory(prefix="prague-radar-") as temp_name:
        temp = Path(temp_name)
        if existing and existing.exists():
            _safe_extract(existing, temp)

        frames = temp / "frames"
        frames.mkdir(parents=True, exist_ok=True)
        manifest_path = temp / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {
                "schema": 1,
                "day_utc": day,
                "source": INDEX_URL,
                "license": "CC BY 4.0",
                "attribution": "Cesky hydrometeorologicky ustav (CHMI)",
                "sampling_minutes": 15,
                "files": {},
            }

        changed = False
        files_manifest: dict[str, dict[str, str]] = manifest.setdefault("files", {})
        for item in candidates:
            destination = frames / item.name
            if destination.exists():
                continue
            partial = destination.with_suffix(".part")
            partial.write_bytes(fetch_bytes(item.url))
            _valid_hdf(partial)
            partial.replace(destination)
            files_manifest[item.name] = {
                "timestamp_utc": item.timestamp.isoformat().replace("+00:00", "Z"),
                "sha256": sha256_file(destination),
                "source": item.url,
            }
            changed = True

        if not changed and existing and existing.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(existing, output)
        elif files_manifest:
            manifest["files"] = dict(sorted(files_manifest.items()))
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            _write_deterministic_archive(temp, output)

    return {
        "day": day,
        "available_slots": len(candidates),
        "archived_slots": len(files_manifest),
        "changed": changed,
        "output": str(output) if output.exists() else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archive one UTC day of CHMI radar data")
    parser.add_argument("--day", required=True, help="UTC day in YYYY-MM-DD format")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--existing", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = collect_day(args.day, args.output, args.existing)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

