#!/usr/bin/env python3
"""Safe project-tree and build-report helpers shared by tooling CLIs."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Any

from spec_lib import canonical_json_bytes, normalized_spec, sha256_bytes, sha256_file


REPORT_VERSION = 1
TEMPLATE_VERSION = 1
GENERATOR_ID = "prompt-to-godot-graybox/new_project.py"
REFRESH_ID = "prompt-to-godot-graybox/refresh_manifest.py"
MANIFEST_SOURCES = {GENERATOR_ID, REFRESH_ID}
REPORT_FIELDS = {
    "report_version",
    "spec_version",
    "template_version",
    "generator",
    "game_title",
    "spec_sha256",
    "template_manifest_sha256",
    "workspace_revision",
    "manifest_source",
    "last_manifest_reason",
    "files",
}
REQUIRED_PATH_TYPES = {
    "project.godot": "file",
    "main.tscn": "file",
    "scripts": "directory",
    "data/game_spec.json": "file",
    "build-report.json": "file",
    "tests/validate_project.gd": "file",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ROOT_GODOT_CACHE = ".godot"
IGNORED_REGULAR_FILE_NAMES = {".DS_Store"}


def scan_safe_tree(project: Path) -> tuple[set[str], set[str], list[str]]:
    """lstat a tree without following links; reject unsafe entries.

    Godot's root ``.godot`` directory is a reproducible import cache, so a real
    directory with that exact root-relative name is excluded from the logical
    project tree. The type check intentionally happens first: a symlink or
    special file named ``.godot`` is still rejected. Nested directories with
    the same name are ordinary project content and are scanned and manifested.
    Regular ``.DS_Store`` files are harmless host metadata and are omitted only
    after their type has also been checked.
    """

    files: set[str] = set()
    directories: set[str] = set()
    errors: list[str] = []
    try:
        root_stat = os.lstat(project)
    except OSError as exc:
        return files, directories, [f"project directory cannot be inspected: {exc}"]
    if stat.S_ISLNK(root_stat.st_mode):
        return files, directories, ["project path must not be a symlink"]
    if not stat.S_ISDIR(root_stat.st_mode):
        return files, directories, ["project directory does not exist or is not a directory"]

    stack: list[tuple[Path, str]] = [(project, "")]
    while stack:
        directory, prefix = stack.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            errors.append(f"cannot inspect directory {prefix or '.'}: {exc}")
            continue
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                errors.append(f"cannot lstat project path {relative}: {exc}")
                continue
            mode = entry_stat.st_mode
            if stat.S_ISLNK(mode):
                errors.append(f"symlink is not allowed in project tree: {relative}")
            elif stat.S_ISDIR(mode):
                if not prefix and entry.name == ROOT_GODOT_CACHE:
                    continue
                directories.add(relative)
                stack.append((Path(entry.path), relative))
            elif stat.S_ISREG(mode):
                if entry.name in IGNORED_REGULAR_FILE_NAMES:
                    continue
                files.add(relative)
            else:
                errors.append(f"special file is not allowed in project tree: {relative}")
    return files, directories, errors


def check_required_types(files: set[str], directories: set[str]) -> list[str]:
    errors: list[str] = []
    for relative, expected_type in REQUIRED_PATH_TYPES.items():
        if expected_type == "file":
            if relative not in files:
                actual = "directory" if relative in directories else "missing"
                errors.append(
                    f"required path must be a regular file: {relative} (found {actual})"
                )
        elif relative not in directories:
            actual = "file" if relative in files else "missing"
            errors.append(
                f"required path must be a directory: {relative} (found {actual})"
            )
    return errors


def manifest_for_files(project: Path, files: set[str]) -> dict[str, str]:
    """Hash a pre-lstatted safe set, excluding the self-referential report."""

    return {
        relative: sha256_file(project / relative)
        for relative in sorted(files)
        if relative != "build-report.json"
    }


def check_report_metadata(report: Any, spec: dict[str, Any]) -> list[str]:
    """Validate non-manifest report metadata against a previously validated spec."""

    errors: list[str] = []
    if not isinstance(report, dict):
        return ["build-report.json: expected an object"]
    if set(report) != REPORT_FIELDS:
        errors.append("build-report.json: unexpected or missing report fields")
    if report.get("report_version") != REPORT_VERSION:
        errors.append(f"build-report.json: report_version must be {REPORT_VERSION}")
    if report.get("spec_version") != 1:
        errors.append("build-report.json: spec_version must be 1")
    if report.get("template_version") != TEMPLATE_VERSION:
        errors.append(f"build-report.json: template_version must be {TEMPLATE_VERSION}")
    if report.get("generator") != GENERATOR_ID:
        errors.append("build-report.json: generator identifier is invalid")
    if report.get("game_title") != spec.get("game", {}).get("title"):
        errors.append("build-report.json: game_title does not match game_spec.json")
    expected_spec_hash = sha256_bytes(canonical_json_bytes(normalized_spec(spec)))
    if report.get("spec_sha256") != expected_spec_hash:
        errors.append("build-report.json: spec_sha256 does not match game_spec.json")
    template_hash = report.get("template_manifest_sha256")
    if not isinstance(template_hash, str) or SHA256_PATTERN.fullmatch(template_hash) is None:
        errors.append("build-report.json: template_manifest_sha256 is invalid")
    revision = report.get("workspace_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        errors.append("build-report.json: workspace_revision must be an integer at least 1")
    if report.get("manifest_source") not in MANIFEST_SOURCES:
        errors.append("build-report.json: manifest_source is invalid")
    reason = report.get("last_manifest_reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        errors.append(
            "build-report.json: last_manifest_reason must be 1-500 non-whitespace characters"
        )
    return errors
