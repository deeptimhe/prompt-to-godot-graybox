#!/usr/bin/env python3
"""Safely accept deliberate edits by rebuilding a generated project's manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from project_lib import (
    REFRESH_ID,
    SHA256_PATTERN,
    check_report_metadata,
    check_required_types,
    manifest_for_files,
    scan_safe_tree,
)
from spec_lib import validate_spec


EXIT_FAILED = 1
EXIT_USAGE = 64
EXIT_IO = 66
DENIED_TREE_COMPONENTS = {".git", "__pycache__"}


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    args.reason = args.reason.strip()
    if not args.reason or len(args.reason) > 500:
        parser.error("--reason must contain 1-500 non-whitespace characters")
    return args


def emit(payload: dict[str, Any], output_format: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stream)
    elif payload["status"] == "REFRESHED":
        print(
            f"REFRESHED {payload['project']}: revision {payload['workspace_revision']}, "
            f"{payload['file_count']} files",
            file=stream,
        )
    else:
        print(f"FAILED {payload['project']}: {payload['message']}", file=stream)
        for message in payload.get("errors", []):
            print(f"- {message}", file=stream)


def _load_json(path: Path, label: str, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{label}: cannot read: {exc}")
    except json.JSONDecodeError as exc:
        errors.append(
            f"{label}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        )
    return None


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".build-report.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return int(exc.code)

    project = Path(os.path.abspath(args.project.expanduser()))
    files, directories, errors = scan_safe_tree(project)
    errors.extend(check_required_types(files, directories))
    for relative in sorted(files | directories):
        if any(part in DENIED_TREE_COMPONENTS for part in Path(relative).parts):
            errors.append(f"generated project tree contains denied runtime/VCS path: {relative}")

    spec: Any | None = None
    report: Any | None = None
    if not errors:
        spec = _load_json(project / "data" / "game_spec.json", "data/game_spec.json", errors)
        report = _load_json(project / "build-report.json", "build-report.json", errors)
    if spec is None and not errors:
        errors.append("data/game_spec.json: expected a v1 JSON object")
    elif spec is not None:
        errors.extend(f"data/game_spec.json: {error}" for error in validate_spec(spec))
    if report is None and not errors:
        errors.append("build-report.json: expected a generated build report object")
    if isinstance(spec, dict) and not validate_spec(spec) and report is not None:
        errors.extend(check_report_metadata(report, spec))
    if isinstance(report, dict):
        old_manifest = report.get("files")
        if not isinstance(old_manifest, dict) or not old_manifest:
            errors.append("build-report.json: existing files manifest must be non-empty")
        else:
            for relative, digest in old_manifest.items():
                if (
                    not isinstance(relative, str)
                    or not relative
                    or relative.startswith("/")
                    or "\\" in relative
                    or ".." in Path(relative).parts
                    or Path(relative).as_posix() != relative
                    or relative == "build-report.json"
                ):
                    errors.append(
                        f"build-report.json: existing manifest has unsafe path {relative!r}"
                    )
                if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
                    errors.append(
                        f"build-report.json: existing manifest has invalid hash for {relative!r}"
                    )
    if errors:
        emit(
            {
                "status": "FAILED",
                "project": str(project),
                "message": f"manifest refresh refused with {len(errors)} error(s)",
                "errors": errors,
            },
            args.format,
            error=True,
        )
        return EXIT_FAILED

    assert isinstance(report, dict)
    try:
        report["files"] = manifest_for_files(project, files)
        report["workspace_revision"] += 1
        report["manifest_source"] = REFRESH_ID
        report["last_manifest_reason"] = args.reason
        _atomic_write_json(project / "build-report.json", report)
    except OSError as exc:
        emit(
            {
                "status": "FAILED",
                "project": str(project),
                "message": "could not write refreshed manifest",
                "errors": [str(exc)],
            },
            args.format,
            error=True,
        )
        return EXIT_IO

    emit(
        {
            "status": "REFRESHED",
            "project": str(project),
            "workspace_revision": report["workspace_revision"],
            "manifest_source": report["manifest_source"],
            "last_manifest_reason": report["last_manifest_reason"],
            "file_count": len(report["files"]),
        },
        args.format,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
