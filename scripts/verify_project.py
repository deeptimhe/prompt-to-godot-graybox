#!/usr/bin/env python3
"""Verify a generated Godot project statically and with Godot headless."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from project_lib import (
    REPORT_FIELDS,
    SHA256_PATTERN,
    check_report_metadata,
    check_required_types,
    scan_safe_tree,
)
from spec_lib import sha256_file, validate_spec


EXIT_FAILED = 1
EXIT_BLOCKED = 2
EXIT_USAGE = 64
EXIT_IO = 66
EXPECTED_PASS_MARKER = "PASS: prompt-to-godot-graybox runtime validation"
MECHANIC_NAMES = (
    "controller",
    "camera",
    "hazard",
    "moving_platform",
    "collectible",
    "switch",
    "door",
    "goal",
    "restart",
)
SPEC_MECHANIC_NAMES = (
    "hazard",
    "moving_platform",
    "collectible",
    "switch",
    "door",
    "goal",
)
MECHANIC_PATTERN = re.compile(
    r"^MECHANIC (controller|camera|hazard|moving_platform|collectible|switch|door|goal|restart) "
    r"(PASS|N/A) count=(\d+)$"
)
ALLOWED_GODOT_ERROR_PATTERNS = (
    re.compile(r"^ERROR: Failed to open 'user://logs/[^']+\.log'\.$"),
    re.compile(r"^ERROR: Failed to open log file for writing: user://logs/[^ ]+\.log$"),
    re.compile(r"^ERROR: Cannot save file '.*/Godot/editor_settings-4\.\d+\.tres'\.$"),
    re.compile(r"^ERROR: Error saving editor settings to .*/Godot/editor_settings-4\.\d+\.tres$"),
)
MACOS_CA_ERROR = 'ERROR: Condition "ret != noErr" is true. Returning: ""'


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", type=Path, help="generated Godot project directory")
    parser.add_argument("--project", dest="project_option", type=Path, help="generated Godot project directory")
    parser.add_argument("--godot", type=Path, help="Godot 4 executable")
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="explicitly skip runtime verification (never reports full verification)",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )
    args = parser.parse_args(argv)
    if args.project is not None and args.project_option is not None:
        parser.error("pass the project either positionally or with --project, not both")
    args.project = args.project_option or args.project
    if args.project is None:
        parser.error("a project directory is required")
    return args


def emit(payload: dict[str, Any], output_format: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stream)
        return
    print(f"{payload['status']} {payload['project']}: {payload['message']}", file=stream)
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


def _static_checks(project: Path) -> list[str]:
    errors: list[str] = []
    files_on_disk, directories, tree_errors = scan_safe_tree(project)
    errors.extend(tree_errors)
    errors.extend(check_required_types(files_on_disk, directories))
    if errors:
        return errors

    spec = _load_json(project / "data" / "game_spec.json", "data/game_spec.json", errors)
    if spec is not None:
        errors.extend(f"data/game_spec.json: {error}" for error in validate_spec(spec))

    report = _load_json(project / "build-report.json", "build-report.json", errors)
    if isinstance(report, dict):
        if isinstance(spec, dict) and not validate_spec(spec):
            errors.extend(check_report_metadata(report, spec))
        elif set(report) != REPORT_FIELDS:
            errors.append("build-report.json: unexpected or missing report fields")
        files = report.get("files")
        if not isinstance(files, dict) or not files:
            errors.append("build-report.json: files must be a non-empty object")
        else:
            manifest_paths: set[str] = set()
            for relative in sorted(files, key=lambda value: str(value)):
                expected_hash = files[relative]
                if (
                    not isinstance(relative, str)
                    or not relative
                    or relative.startswith("/")
                    or "\\" in relative
                    or ".." in Path(relative).parts
                    or Path(relative).as_posix() != relative
                    or relative == "build-report.json"
                ):
                    errors.append(f"build-report.json: unsafe file path {relative!r}")
                    continue
                manifest_paths.add(relative)
                path = project / relative
                if not isinstance(expected_hash, str) or SHA256_PATTERN.fullmatch(
                    expected_hash
                ) is None:
                    errors.append(f"build-report.json: invalid hash for {relative}")
                elif relative in files_on_disk and sha256_file(path) != expected_hash:
                    errors.append(f"build-report.json: file hash mismatch: {relative}")

            expected_paths = files_on_disk - {"build-report.json"}
            for relative in sorted(expected_paths - manifest_paths):
                errors.append(f"build-report.json: unlisted project file: {relative}")
            for relative in sorted(manifest_paths - expected_paths):
                errors.append(f"build-report.json: listed file is missing: {relative}")

    try:
        project_config = (project / "project.godot").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"project.godot: cannot read: {exc}")
    else:
        main_match = re.search(r'^run/main_scene\s*=\s*"res://([^"\r\n]+)"', project_config, re.MULTILINE)
        if main_match is None:
            errors.append("project.godot: run/main_scene is missing")
        else:
            main_scene = main_match.group(1)
            if (
                main_scene.startswith("/")
                or "\\" in main_scene
                or ".." in Path(main_scene).parts
                or Path(main_scene).as_posix() != main_scene
            ):
                errors.append(f"project.godot: run/main_scene path is unsafe: {main_scene}")
            elif main_scene not in files_on_disk:
                errors.append(
                    f"project.godot: run/main_scene target is missing: {main_scene}"
                )
    return errors


def _find_godot(explicit: Path | None) -> Path | None:
    if explicit is not None:
        candidate = explicit.expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
        return None
    candidates: list[Path] = []
    env_path = os.environ.get("GODOT_BIN")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    for command in ("godot4", "godot"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    candidates.extend(
        [
            Path("/Applications/Godot.app/Contents/MacOS/Godot"),
            Path("/tmp/godot472/Godot.app/Contents/MacOS/Godot"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


def _tail(text: str, line_count: int = 40) -> str:
    return "\n".join(text.splitlines()[-line_count:])


def _godot_errors(output: str) -> list[str]:
    errors: list[str] = []
    output_lines = output.splitlines()
    for index, raw_line in enumerate(output_lines):
        line = raw_line.strip()
        suspicious = (
            line.startswith("SCRIPT ERROR:")
            or line.startswith("ERROR:")
            or "Parse Error:" in line
            or "SCRIPT FAILED:" in line
        )
        if not suspicious:
            continue
        if any(pattern.fullmatch(line) for pattern in ALLOWED_GODOT_ERROR_PATTERNS):
            continue
        if line == MACOS_CA_ERROR:
            next_line = output_lines[index + 1].strip() if index + 1 < len(output_lines) else ""
            if next_line.startswith("at: get_system_ca_certificates "):
                continue
        errors.append(line)
    return errors


def _expected_mechanics(spec: dict[str, Any]) -> dict[str, tuple[str, int]]:
    counts = {name: 0 for name in SPEC_MECHANIC_NAMES}
    for item in spec["objects"]:
        object_type = item["type"]
        if object_type in counts:
            counts[object_type] += 1
    expected: dict[str, tuple[str, int]] = {
        "controller": ("PASS", 1),
        "camera": ("PASS", 1),
        "restart": ("PASS", 1),
    }
    for name in SPEC_MECHANIC_NAMES:
        count = counts[name]
        expected[name] = ("PASS" if count else "N/A", count)
    return {name: expected[name] for name in MECHANIC_NAMES}


def _mechanic_evidence(
    output: str, spec: dict[str, Any]
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    observed: dict[str, tuple[str, int, str]] = {}
    for line in output.splitlines():
        if not line.startswith("MECHANIC "):
            continue
        match = MECHANIC_PATTERN.fullmatch(line)
        if match is None:
            errors.append(f"malformed mechanic evidence line: {line!r}")
            continue
        name, status, count_text = match.groups()
        if name in observed:
            errors.append(f"duplicate mechanic evidence line for {name}")
            continue
        observed[name] = (status, int(count_text), line)

    expected = _expected_mechanics(spec)
    evidence: dict[str, dict[str, Any]] = {}
    for name in MECHANIC_NAMES:
        expected_status, expected_count = expected[name]
        value = observed.get(name)
        if value is None:
            errors.append(f"missing mechanic evidence line for {name}")
            continue
        status, count, line = value
        evidence[name] = {"status": status, "count": count, "line": line}
        if (status, count) != (expected_status, expected_count):
            errors.append(
                f"mechanic evidence mismatch for {name}: expected "
                f"{expected_status} count={expected_count}, got {status} count={count}"
            )
    return errors, evidence


def _run(command: list[str], timeout: int) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout


def _copy_runtime_project(project: Path, destination: Path) -> None:
    """Copy a project without reusing its root Godot import cache.

    Only the root ``.godot`` directory is omitted. A nested directory with the
    same name is project content and must not gain an ignore-path escape hatch.
    Static verification has already rejected a root symlink named ``.godot``.
    """

    def ignore_root_cache(directory: str, names: list[str]) -> set[str]:
        if Path(directory) == project and ".godot" in names:
            return {".godot"}
        return set()

    shutil.copytree(project, destination, ignore=ignore_root_cache)


def _runtime_checks(
    project: Path, godot: Path, spec: dict[str, Any]
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    checks: list[str] = []
    evidence: dict[str, Any] = {
        "godot_version": None,
        "import_exit_code": None,
        "exit_code": None,
        "marker": None,
        "mechanics": {},
    }
    try:
        version_code, version_output = _run([str(godot), "--version"], timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"cannot execute Godot: {exc}"], checks, evidence
    if version_code != 0:
        evidence["exit_code"] = version_code
        return [f"Godot --version failed:\n{_tail(version_output)}"], checks, evidence
    version = version_output.strip().splitlines()[0] if version_output.strip() else "unknown"
    evidence["godot_version"] = version
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:\.|$)", version)
    detected_version = (
        (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))
        if match is not None
        else None
    )
    if (
        detected_version is None
        or detected_version[0] != 4
        or detected_version < (4, 7, 2)
    ):
        return [f"Godot 4.7.2 or newer in major version 4 is required; detected {version!r}"], checks, evidence
    checks.append(f"godot_version:{version}")

    runtime_context: tempfile.TemporaryDirectory[str] | None = None
    runtime_project = project
    if project.is_dir():
        try:
            runtime_context = tempfile.TemporaryDirectory(prefix="godot-graybox-verify-")
            runtime_project = Path(runtime_context.name) / "project"
            _copy_runtime_project(project, runtime_project)
        except OSError as exc:
            if runtime_context is not None:
                runtime_context.cleanup()
            return [f"cannot prepare isolated runtime project: {exc}"], checks, evidence
    command = [
        str(godot),
        "--headless",
        "--path",
        str(runtime_project),
        "--script",
        "res://tests/validate_project.gd",
    ]
    try:
        import_command = [
            str(godot),
            "--headless",
            "--path",
            str(runtime_project),
            "--import",
        ]
        try:
            import_code, import_output = _run(import_command, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [f"import check could not complete: {exc}"], checks, evidence
        evidence["import_exit_code"] = import_code
        if import_code != 0:
            return [f"import check failed with exit {import_code}:\n{_tail(import_output)}"], checks, evidence
        import_errors = _godot_errors(import_output)
        if import_errors:
            return [
                "import check logged Godot errors despite exit zero:\n"
                + _tail("\n".join(import_errors))
            ], checks, evidence
        checks.append("import")

        try:
            return_code, output = _run(command, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [f"behavior check could not complete: {exc}"], checks, evidence
        evidence["exit_code"] = return_code
        if return_code != 0:
            errors.append(f"behavior check failed with exit {return_code}:\n{_tail(output)}")
            return errors, checks, evidence
        logged_errors = _godot_errors(output)
        if logged_errors:
            errors.append(
                "behavior check logged Godot errors despite exit zero:\n"
                + _tail("\n".join(logged_errors))
            )
            return errors, checks, evidence
        mechanic_errors, mechanics = _mechanic_evidence(output, spec)
        evidence["mechanics"] = mechanics
        errors.extend(mechanic_errors)
        marker_present = EXPECTED_PASS_MARKER in output.splitlines()
        evidence["marker"] = EXPECTED_PASS_MARKER if marker_present else None
        if not marker_present:
            errors.append(
                f"behavior check exited zero without exact pass marker {EXPECTED_PASS_MARKER!r}"
            )
        if not errors:
            checks.append("behavior")
    finally:
        if runtime_context is not None:
            runtime_context.cleanup()
    return errors, checks, evidence


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return int(exc.code)

    project = Path(os.path.abspath(args.project.expanduser()))
    static_errors = _static_checks(project)
    if static_errors:
        emit(
            {
                "status": "FAILED",
                "project": str(project),
                "message": f"static verification found {len(static_errors)} error(s)",
                "errors": static_errors,
                "godot_version": None,
                "exit_code": None,
                "marker": None,
                "mechanics": {},
                "checks": [],
            },
            args.format,
            error=True,
        )
        return EXIT_FAILED
    if args.static_only:
        emit(
            {
                "status": "VERIFIED_STATIC",
                "project": str(project),
                "message": "static checks passed; runtime verification was explicitly skipped",
                "checks": ["structure", "schema", "manifest"],
                "godot_version": None,
                "exit_code": None,
                "marker": None,
                "mechanics": {},
            },
            args.format,
        )
        return 0

    godot = _find_godot(args.godot)
    if godot is None:
        emit(
            {
                "status": "BLOCKED",
                "project": str(project),
                "message": "static checks passed, but no executable Godot 4 was found; pass --godot or use --static-only",
                "godot_version": None,
                "exit_code": None,
                "marker": None,
                "mechanics": {},
                "checks": ["structure", "schema", "manifest"],
            },
            args.format,
            error=True,
        )
        return EXIT_BLOCKED

    spec = json.loads((project / "data" / "game_spec.json").read_text(encoding="utf-8"))
    runtime_errors, runtime_checks, evidence = _runtime_checks(project, godot, spec)
    if runtime_errors:
        emit(
            {
                "status": "FAILED",
                "project": str(project),
                "message": "Godot runtime verification failed",
                "errors": runtime_errors,
                "godot": str(godot),
                "godot_version": evidence["godot_version"],
                "exit_code": evidence["exit_code"],
                "marker": evidence["marker"],
                "mechanics": evidence["mechanics"],
                "checks": ["structure", "schema", "manifest"] + runtime_checks,
            },
            args.format,
            error=True,
        )
        return EXIT_FAILED
    emit(
        {
            "status": "VERIFIED",
            "project": str(project),
            "message": "static and Godot runtime checks passed",
            "checks": ["structure", "schema", "manifest"] + runtime_checks,
            "godot": str(godot),
            "godot_version": evidence["godot_version"],
            "exit_code": evidence["exit_code"],
            "marker": evidence["marker"],
            "mechanics": evidence["mechanics"],
        },
        args.format,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
