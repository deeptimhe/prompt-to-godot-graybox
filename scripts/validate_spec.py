#!/usr/bin/env python3
"""Validate a prompt-to-Godot graybox v1 JSON specification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from spec_lib import validate_spec


EXIT_VALIDATION = 1
EXIT_USAGE = 64
EXIT_JSON = 65
EXIT_IO = 66


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="path to a v1 game spec JSON file")
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
    if status == "VALID":
        print(
            f"VALID {payload['spec']}: {payload['object_count']} objects",
            file=stream,
        )
    else:
        print(
            f"{status} {payload['spec']} ({payload.get('error_count', 1)} error(s))",
            file=stream,
        )
        for message in payload.get("errors", []):
            print(f"- {message}", file=stream)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        raw = args.spec.read_text(encoding="utf-8")
    except OSError as exc:
        emit(
            {
                "status": "IO_ERROR",
                "spec": str(args.spec),
                "error_count": 1,
                "errors": [str(exc)],
            },
            args.format,
            error=True,
        )
        return EXIT_IO
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        emit(
            {
                "status": "JSON_ERROR",
                "spec": str(args.spec),
                "error_count": 1,
                "errors": [f"line {exc.lineno}, column {exc.colno}: {exc.msg}"],
            },
            args.format,
            error=True,
        )
        return EXIT_JSON

    errors = validate_spec(data)
    if errors:
        emit(
            {
                "status": "INVALID",
                "spec": str(args.spec),
                "error_count": len(errors),
                "errors": errors,
            },
            args.format,
            error=True,
        )
        return EXIT_VALIDATION

    emit(
        {
            "status": "VALID",
            "spec": str(args.spec),
            "error_count": 0,
            "object_count": len(data["objects"]),
        },
        args.format,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
