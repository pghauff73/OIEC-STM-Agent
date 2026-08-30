from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import os
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


ROOT = Path(__file__).resolve().parents[1]


def _project() -> Dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _distribution_name() -> str:
    return _project()["name"].replace("-", "_")


def _dist_info() -> str:
    return f"{_distribution_name()}-{_project()['version']}.dist-info"


def _source_files() -> Iterable[tuple[Path, str]]:
    for package in ("ourd", "ourd_gui"):
        for path in sorted((ROOT / package).rglob("*.py")):
            yield path, path.relative_to(ROOT).as_posix()
    for name in ("oiec_stm_agent.py", "ourd_agent.py", "egcf.py"):
        path = ROOT / name
        yield path, name
    for directory in ("algorithms", "commands", "schemas", "workflows"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file():
                yield path, path.relative_to(ROOT).as_posix()


def _metadata() -> str:
    project = _project()
    lines = [
        "Metadata-Version: 2.3",
        f"Name: {project['name']}",
        f"Version: {project['version']}",
        f"Summary: {project.get('description', '')}",
        f"Requires-Python: {project.get('requires-python', '')}",
    ]
    for requirement in project.get("dependencies", []):
        lines.append(f"Requires-Dist: {requirement}")
    for extra, requirements in project.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra}")
        for requirement in requirements:
            lines.append(f"Requires-Dist: {requirement}; extra == '{extra}'")
    return "\n".join(lines) + "\n"


def _wheel_metadata() -> str:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: ourd-local-build-backend 1\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )


def _entry_points() -> str:
    scripts = _project().get("scripts", {})
    lines = ["[console_scripts]"]
    lines.extend(f"{name} = {target}" for name, target in sorted(scripts.items()))
    return "\n".join(lines) + "\n"


def _record_digest(content: bytes) -> str:
    digest = hashlib.sha256(content).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 8, 21, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def get_requires_for_build_wheel(config_settings: Optional[Dict[str, Any]] = None) -> list[str]:
    return []


def get_requires_for_build_sdist(config_settings: Optional[Dict[str, Any]] = None) -> list[str]:
    return []


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
) -> str:
    dist_info = _dist_info()
    target = Path(metadata_directory) / dist_info
    target.mkdir(parents=True, exist_ok=True)
    (target / "METADATA").write_text(_metadata(), encoding="utf-8")
    (target / "WHEEL").write_text(_wheel_metadata(), encoding="utf-8")
    (target / "entry_points.txt").write_text(_entry_points(), encoding="utf-8")
    return dist_info


def build_wheel(
    wheel_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
    metadata_directory: Optional[str] = None,
) -> str:
    project = _project()
    filename = f"{_distribution_name()}-{project['version']}-py3-none-any.whl"
    destination = Path(wheel_directory) / filename
    dist_info = _dist_info()
    entries: list[tuple[str, bytes]] = []
    for path, archive_name in _source_files():
        entries.append((archive_name, path.read_bytes()))
    entries.extend(
        [
            (f"{dist_info}/METADATA", _metadata().encode("utf-8")),
            (f"{dist_info}/WHEEL", _wheel_metadata().encode("utf-8")),
            (f"{dist_info}/entry_points.txt", _entry_points().encode("utf-8")),
            (
                f"{dist_info}/top_level.txt",
                b"ourd\nourd_gui\noiec_stm_agent\nourd_agent\negcf\n",
            ),
        ]
    )
    records = [[name, _record_digest(content), str(len(content))] for name, content in entries]
    record_path = f"{dist_info}/RECORD"
    record_buffer = io.StringIO(newline="")
    writer = csv.writer(record_buffer, lineterminator="\n")
    writer.writerows(records)
    writer.writerow([record_path, "", ""])
    entries.append((record_path, record_buffer.getvalue().encode("utf-8")))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        for name, content in entries:
            archive.writestr(_zip_info(name), content)
    return filename


def build_sdist(
    sdist_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
) -> str:
    project = _project()
    prefix = f"{project['name']}-{project['version']}"
    filename = f"{prefix}.tar.gz"
    destination = Path(sdist_directory) / filename
    included = [
        ROOT / "pyproject.toml",
        ROOT / "README.md",
        ROOT / "oiec_stm_agent.py",
        ROOT / "ourd_agent.py",
        ROOT / "egcf.py",
        *sorted((ROOT / "ourd").rglob("*.py")),
        *sorted((ROOT / "ourd_gui").rglob("*.py")),
        *sorted((ROOT / "tools").glob("*.py")),
        *[
            path
            for directory in (
                "algorithms",
                "benchmarks",
                "commands",
                "schemas",
                "workflows",
                "docs",
            )
            for path in sorted((ROOT / directory).rglob("*"))
            if path.is_file()
        ],
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as destination_handle:
        with gzip.GzipFile(fileobj=destination_handle, mode="wb", mtime=0) as gzip_handle:
            with tarfile.open(
                fileobj=gzip_handle,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for path in included:
                    info = archive.gettarinfo(
                        str(path),
                        arcname=f"{prefix}/{path.relative_to(ROOT)}",
                    )
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)
    return filename
