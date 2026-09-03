#!/usr/bin/env python3
"""Generate a deterministic playable Godot project from a validated v1 spec."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from spec_lib import (
    canonical_json_bytes,
    normalized_spec,
    sha256_bytes,
    sha256_file,
    validate_spec,
    write_json,
)
from project_lib import (
    GENERATOR_ID,
    TEMPLATE_VERSION,
    manifest_for_files,
    scan_safe_tree,
)


EXIT_VALIDATION = 1
EXIT_USAGE = 64
EXIT_JSON = 65
EXIT_IO = 66
EXIT_CANT_CREATE = 73

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = SKILL_ROOT / "assets" / "godot-template"
IGNORED_NAMES = {".DS_Store", ".git", ".godot", "__pycache__"}
REQUIRED_TEMPLATE_PATHS = ("project.godot", "main.tscn", "scripts")


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="v1 game spec JSON")
    parser.add_argument("--output", required=True, type=Path, help="new project directory")
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="template override (defaults to this skill's bundled template)",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )
    return parser.parse_args(argv)


def emit(payload: dict[str, Any], output_format: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stream)
        return
    status = payload["status"]
    if status == "CREATED":
        print(
            f"CREATED {payload['output']}: {payload['file_count']} files, "
            f"spec {payload['spec_sha256'][:12]}",
            file=stream,
        )
    else:
        print(f"{status}: {payload['message']}", file=stream)
        for message in payload.get("errors", []):
            print(f"- {message}", file=stream)


def _read_spec(
    path: Path,
) -> tuple[dict[str, Any] | None, bytes | None, str | None, int]:
    try:
        source = path.read_bytes()
    except OSError as exc:
        return None, None, str(exc), EXIT_IO
    try:
        raw = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, None, f"spec is not valid UTF-8: {exc}", EXIT_JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return (
            None,
            None,
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            EXIT_JSON,
        )
    return data, source, None, 0


def _check_template(template: Path) -> list[str]:
    errors: list[str] = []
    if not template.is_dir():
        return [f"template directory does not exist: {template}"]
    for relative in REQUIRED_TEMPLATE_PATHS:
        if not (template / relative).exists():
            errors.append(f"template is missing {relative}")
    return errors


def _should_ignore(path: Path, template: Path) -> bool:
    try:
        relative = path.relative_to(template)
    except ValueError:
        return True
    return any(part in IGNORED_NAMES for part in relative.parts)


def _copy_template(template: Path, destination: Path) -> None:
    for source in sorted(template.rglob("*"), key=lambda path: path.as_posix()):
        if _should_ignore(source, template):
            continue
        relative = source.relative_to(template)
        target = destination / relative
        if source.is_symlink():
            raise OSError(f"template symlinks are not supported: {relative.as_posix()}")
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def _set_project_title(project_file: Path, title: str) -> None:
    source = project_file.read_text(encoding="utf-8")
    replacement = f"config/name={json.dumps(title, ensure_ascii=False)}"
    updated, count = re.subn(
        r'^config/name\s*=\s*"(?:[^"\\]|\\.)*"\s*$',
        lambda _match: replacement,
        source,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise OSError("template project.godot must contain exactly one config/name string")
    project_file.write_text(updated, encoding="utf-8")


def _file_manifest(project: Path) -> dict[str, str]:
    files, _directories, errors = scan_safe_tree(project)
    if errors:
        raise OSError("; ".join(errors))
    return manifest_for_files(project, files)


def _template_manifest(template: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(template.rglob("*"), key=lambda item: item.as_posix()):
        if _should_ignore(path, template) or not path.is_file():
            continue
        manifest[path.relative_to(template).as_posix()] = sha256_file(path)
    return manifest


def _write_generated_data(
    project: Path, spec: dict[str, Any], source_spec: bytes
) -> None:
    game_spec_path = project / "data" / "game_spec.json"
    game_spec_path.parent.mkdir(parents=True, exist_ok=True)
    game_spec_path.write_bytes(source_spec)
    write_json(
        project / "data" / "level.json",
        {
            "version": spec["version"],
            "spawn": spec["spawn"],
            "objects": spec["objects"],
        },
    )
    write_json(
        project / "data" / "gameplay.json",
        {
            "version": spec["version"],
            "game": spec["game"],
            "player": spec["player"],
            "camera": spec["camera"],
        },
    )


def _build_project(
    spec: dict[str, Any], source_spec: bytes, template: Path, project: Path
) -> dict[str, Any]:
    template_hashes = _template_manifest(template)
    _copy_template(template, project)
    _write_generated_data(project, spec, source_spec)
    _set_project_title(project / "project.godot", spec["game"]["title"])

    manifest = _file_manifest(project)
    report = {
        "report_version": 1,
        "spec_version": spec["version"],
        "template_version": TEMPLATE_VERSION,
        "generator": GENERATOR_ID,
        "game_title": spec["game"]["title"],
        "spec_sha256": sha256_bytes(canonical_json_bytes(spec)),
        "template_manifest_sha256": sha256_bytes(canonical_json_bytes(template_hashes)),
        "workspace_revision": 1,
        "manifest_source": GENERATOR_ID,
        "last_manifest_reason": "initial generation",
        "files": manifest,
    }
    write_json(project / "build-report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return int(exc.code)

    raw_spec, source_spec, read_error, read_code = _read_spec(args.spec)
    if read_error is not None:
        emit(
            {"status": "ERROR", "message": read_error},
            args.format,
            error=True,
        )
        return read_code
    validation_errors = validate_spec(raw_spec)
    if validation_errors:
        emit(
            {
                "status": "INVALID",
                "message": f"spec failed with {len(validation_errors)} error(s)",
                "errors": validation_errors,
            },
            args.format,
            error=True,
        )
        return EXIT_VALIDATION

    template = args.template.expanduser().resolve()
    template_errors = _check_template(template)
    if template_errors:
        emit(
            {
                "status": "ERROR",
                "message": "template is not usable",
                "errors": template_errors,
            },
            args.format,
            error=True,
        )
        return EXIT_IO

    requested_output = Path(os.path.abspath(args.output.expanduser()))
    if requested_output.is_symlink():
        emit(
            {
                "status": "REFUSED",
                "message": "output path must not be a symlink",
            },
            args.format,
            error=True,
        )
        return EXIT_CANT_CREATE
    output = requested_output.resolve()
    if output == template or template in output.parents:
        emit(
            {
                "status": "REFUSED",
                "message": "output must not be the template directory or a directory inside it",
            },
            args.format,
            error=True,
        )
        return EXIT_CANT_CREATE
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        emit(
            {
                "status": "REFUSED",
                "message": f"output must not exist or must be an empty directory: {output}",
            },
            args.format,
            error=True,
        )
        return EXIT_CANT_CREATE
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        temp_path = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.building-", dir=output.parent)
        )
    except OSError as exc:
        emit(
            {"status": "ERROR", "message": f"cannot prepare output: {exc}"},
            args.format,
            error=True,
        )
        return EXIT_CANT_CREATE

    try:
        report = _build_project(
            normalized_spec(raw_spec), source_spec, template, temp_path
        )
        if output.exists():
            output.rmdir()
        os.replace(temp_path, output)
    except OSError as exc:
        shutil.rmtree(temp_path, ignore_errors=True)
        emit(
            {"status": "ERROR", "message": f"generation failed: {exc}"},
            args.format,
            error=True,
        )
        return EXIT_CANT_CREATE

    emit(
        {
            "status": "CREATED",
            "output": str(output),
            "file_count": len(report["files"]) + 1,
            "spec_sha256": report["spec_sha256"],
        },
        args.format,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
