#!/usr/bin/env python3
"""Shared schema and deterministic utilities for the v1 Godot graybox spec."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


SPEC_VERSION = 1
MAX_OBJECTS = 512
MAX_COORDINATE = 10_000
MAX_ROTATION_DEGREES = 36_000
MIN_SIZE = 0.01
MAX_SIZE = 1_000
MIN_MOVEMENT_DURATION = 0.05
MAX_MOVEMENT_DURATION = 3_600
MAX_PLAYER_SPEED = 100
MAX_PLAYER_TUNING = 500
MAX_COLLECTIBLE_VALUE = 1_000
MAX_TOTAL_COLLECTIBLE_VALUE = 10_000
MAX_REQUIREMENT_SWITCHES = 128
SUPPORTED_TYPES = {
    "static_box",
    "ramp",
    "moving_platform",
    "hazard",
    "collectible",
    "switch",
    "door",
    "goal",
    "marker",
}

ROOT_FIELDS = {"version", "game", "player", "camera", "spawn", "objects"}
GAME_FIELDS = {"title", "objective", "completion_message"}
PLAYER_FIELDS = {
    "walk_speed",
    "sprint_speed",
    "acceleration",
    "deceleration",
    "air_control",
    "turn_speed",
    "gravity",
    "jump_velocity",
}
CAMERA_FIELDS = {"distance", "fov", "initial_pitch_degrees"}
TRANSFORM_FIELDS = {"position", "rotation_degrees"}
COMMON_OBJECT_FIELDS = {"id", "type", "transform", "size", "color"}
MOVEMENT_FIELDS = {"offset", "duration"}
REQUIREMENT_FIELDS = {"collectibles", "switches"}
TYPE_EXTRA_FIELDS = {
    "static_box": set(),
    "ramp": set(),
    "moving_platform": {"movement"},
    "hazard": set(),
    "collectible": {"value"},
    "switch": set(),
    "door": {"requirements"},
    "goal": {"requirements"},
    "marker": set(),
}
TYPE_REQUIRED_FIELDS = {
    "static_box": set(),
    "ramp": set(),
    "moving_platform": {"movement"},
    "hazard": set(),
    "collectible": {"value"},
    "switch": set(),
    "door": set(),
    "goal": set(),
    "marker": set(),
}
UNSUPPORTED_CAPABILITY_FIELDS = {
    "combat",
    "dialogue",
    "enemies",
    "inventory",
    "multiplayer",
    "networking",
    "quests",
    "vehicles",
    "weapons",
}

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")


def is_number(value: Any) -> bool:
    """Return true for finite JSON-style numbers, excluding booleans."""

    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON reproducibly for hashing."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write human-readable deterministic JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    path.write_text(text + "\n", encoding="utf-8")


def _unknown_fields(
    value: dict[str, Any], allowed: set[str], path: str, errors: list[str]
) -> None:
    for field in sorted(set(value) - allowed):
        if field in UNSUPPORTED_CAPABILITY_FIELDS:
            errors.append(
                f"{path}.{field}: unsupported capability in schema v{SPEC_VERSION}"
            )
        else:
            errors.append(f"{path}.{field}: unknown field (schema is fail-closed)")


def _require_fields(
    value: dict[str, Any], required: Iterable[str], path: str, errors: list[str]
) -> None:
    for field in sorted(set(required) - set(value)):
        errors.append(f"{path}.{field}: required field is missing")


def _object(
    value: Any,
    path: str,
    errors: list[str],
    *,
    allowed: set[str] | None = None,
    required: set[str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected an object")
        return None
    if allowed is not None:
        _unknown_fields(value, allowed, path, errors)
    if required is not None:
        _require_fields(value, required, path, errors)
    return value


def _nonempty_string(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: expected a non-empty string")


def _number(
    value: Any,
    path: str,
    errors: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
) -> None:
    if not is_number(value):
        errors.append(f"{path}: expected a finite number")
        return
    if minimum is not None:
        if (minimum_inclusive and value < minimum) or (
            not minimum_inclusive and value <= minimum
        ):
            operator = "at least" if minimum_inclusive else "greater than"
            errors.append(f"{path}: expected a number {operator} {minimum:g}")
    if maximum is not None and value > maximum:
        errors.append(f"{path}: expected a number no greater than {maximum:g}")


def _integer(
    value: Any,
    path: str,
    errors: list[str],
    *,
    minimum: int,
    maximum: int | None = None,
    required: bool = True,
) -> None:
    if value is None and not required:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{path}: expected an integer")
    elif value < minimum:
        errors.append(f"{path}: expected an integer at least {minimum}")
    elif maximum is not None and value > maximum:
        errors.append(f"{path}: expected an integer no greater than {maximum}")


def _vector(
    value: Any,
    path: str,
    errors: list[str],
    *,
    positive: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    absolute_maximum: float | None = None,
) -> None:
    if not isinstance(value, list) or len(value) != 3:
        errors.append(f"{path}: expected an array of 3 finite numbers")
        return
    if not all(is_number(component) for component in value):
        errors.append(f"{path}: expected an array of 3 finite numbers")
        return
    if positive and not all(component > 0 for component in value):
        errors.append(f"{path}: all components must be greater than zero")
    if minimum is not None and any(component < minimum for component in value):
        errors.append(f"{path}: all components must be at least {minimum:g}")
    if maximum is not None and any(component > maximum for component in value):
        errors.append(f"{path}: all components must be no greater than {maximum:g}")
    if absolute_maximum is not None and any(
        abs(component) > absolute_maximum for component in value
    ):
        errors.append(
            f"{path}: component absolute values must be no greater than "
            f"{absolute_maximum:g}"
        )


def _transform(value: Any, path: str, errors: list[str]) -> None:
    transform = _object(
        value,
        path,
        errors,
        allowed=TRANSFORM_FIELDS,
        required=TRANSFORM_FIELDS,
    )
    if transform is None:
        return
    _vector(
        transform.get("position"),
        f"{path}.position",
        errors,
        absolute_maximum=MAX_COORDINATE,
    )
    _vector(
        transform.get("rotation_degrees"),
        f"{path}.rotation_degrees",
        errors,
        absolute_maximum=MAX_ROTATION_DEGREES,
    )


def _requirements(value: Any, path: str, errors: list[str]) -> None:
    requirements = _object(
        value,
        path,
        errors,
        allowed=REQUIREMENT_FIELDS,
        required=REQUIREMENT_FIELDS,
    )
    if requirements is None:
        return
    if "collectibles" in requirements:
        _integer(
            requirements["collectibles"],
            f"{path}.collectibles",
            errors,
            minimum=0,
            maximum=MAX_TOTAL_COLLECTIBLE_VALUE,
        )
    if "switches" in requirements:
        switches = requirements["switches"]
        if not isinstance(switches, list):
            errors.append(f"{path}.switches: expected an array of switch ids")
        else:
            if len(switches) > MAX_REQUIREMENT_SWITCHES:
                errors.append(
                    f"{path}.switches: expected at most {MAX_REQUIREMENT_SWITCHES} entries"
                )
            seen: set[str] = set()
            for index, switch_id in enumerate(switches):
                switch_path = f"{path}.switches[{index}]"
                if not isinstance(switch_id, str) or not ID_PATTERN.fullmatch(switch_id):
                    errors.append(f"{switch_path}: expected a valid object id")
                elif switch_id in seen:
                    errors.append(f"{switch_path}: duplicate switch reference {switch_id!r}")
                else:
                    seen.add(switch_id)


def _validate_game(value: Any, errors: list[str]) -> None:
    game = _object(
        value,
        "game",
        errors,
        allowed=GAME_FIELDS,
        required=GAME_FIELDS,
    )
    if game is None:
        return
    for field in sorted(GAME_FIELDS):
        _nonempty_string(game.get(field), f"game.{field}", errors)


def _validate_player(value: Any, errors: list[str]) -> None:
    player = _object(
        value,
        "player",
        errors,
        allowed=PLAYER_FIELDS,
        required=PLAYER_FIELDS,
    )
    if player is None:
        return
    for field in (
        "walk_speed",
        "sprint_speed",
        "jump_velocity",
    ):
        _number(
            player.get(field),
            f"player.{field}",
            errors,
            minimum=0,
            maximum=MAX_PLAYER_SPEED,
            minimum_inclusive=False,
        )
    for field in (
        "acceleration",
        "deceleration",
        "turn_speed",
        "gravity",
    ):
        _number(
            player.get(field),
            f"player.{field}",
            errors,
            minimum=0,
            maximum=MAX_PLAYER_TUNING,
            minimum_inclusive=False,
        )
    _number(player.get("air_control"), "player.air_control", errors, minimum=0, maximum=1)
    walk_speed = player.get("walk_speed")
    sprint_speed = player.get("sprint_speed")
    if is_number(walk_speed) and is_number(sprint_speed) and sprint_speed < walk_speed:
        errors.append("player.sprint_speed: must be at least player.walk_speed")


def _validate_camera(value: Any, errors: list[str]) -> None:
    camera = _object(
        value,
        "camera",
        errors,
        allowed=CAMERA_FIELDS,
        required=CAMERA_FIELDS,
    )
    if camera is None:
        return
    _number(camera.get("distance"), "camera.distance", errors, minimum=0.5, maximum=20)
    _number(camera.get("fov"), "camera.fov", errors, minimum=20, maximum=120)
    _number(
        camera.get("initial_pitch_degrees"),
        "camera.initial_pitch_degrees",
        errors,
        minimum=-45,
        maximum=45,
    )


def _validate_spawn(value: Any, errors: list[str]) -> None:
    spawn = _object(
        value,
        "spawn",
        errors,
        allowed=TRANSFORM_FIELDS,
        required=TRANSFORM_FIELDS,
    )
    if spawn is None:
        return
    _vector(
        spawn.get("position"),
        "spawn.position",
        errors,
        absolute_maximum=MAX_COORDINATE,
    )
    _vector(
        spawn.get("rotation_degrees"),
        "spawn.rotation_degrees",
        errors,
        absolute_maximum=MAX_ROTATION_DEGREES,
    )


def _validate_object(item: Any, index: int, errors: list[str]) -> None:
    path = f"objects[{index}]"
    if not isinstance(item, dict):
        errors.append(f"{path}: expected an object")
        return

    object_type = item.get("type")
    if object_type not in SUPPORTED_TYPES:
        errors.append(
            f"{path}.type: unsupported object type {object_type!r}; expected one of "
            + ", ".join(sorted(SUPPORTED_TYPES))
        )
        allowed = COMMON_OBJECT_FIELDS
    else:
        allowed = COMMON_OBJECT_FIELDS | TYPE_EXTRA_FIELDS[object_type]
    _unknown_fields(item, allowed, path, errors)
    required = COMMON_OBJECT_FIELDS
    if object_type in TYPE_REQUIRED_FIELDS:
        required = required | TYPE_REQUIRED_FIELDS[object_type]
    _require_fields(item, required, path, errors)

    object_id = item.get("id")
    if not isinstance(object_id, str) or not ID_PATTERN.fullmatch(object_id):
        errors.append(
            f"{path}.id: expected 1-64 characters matching {ID_PATTERN.pattern}"
        )
    _transform(item.get("transform"), f"{path}.transform", errors)
    _vector(
        item.get("size"),
        f"{path}.size",
        errors,
        positive=True,
        minimum=MIN_SIZE,
        maximum=MAX_SIZE,
    )
    color = item.get("color")
    if not isinstance(color, str) or not COLOR_PATTERN.fullmatch(color):
        errors.append(f"{path}.color: expected #RRGGBB or #RRGGBBAA")

    if object_type == "moving_platform":
        movement = _object(
            item.get("movement"),
            f"{path}.movement",
            errors,
            allowed=MOVEMENT_FIELDS,
            required=MOVEMENT_FIELDS,
        )
        if movement is not None:
            offset = movement.get("offset")
            _vector(
                offset,
                f"{path}.movement.offset",
                errors,
                absolute_maximum=MAX_COORDINATE,
            )
            if (
                isinstance(offset, list)
                and len(offset) == 3
                and all(is_number(component) for component in offset)
                and all(component == 0 for component in offset)
            ):
                errors.append(f"{path}.movement.offset: must not be the zero vector")
            _number(
                movement.get("duration"),
                f"{path}.movement.duration",
                errors,
                minimum=MIN_MOVEMENT_DURATION,
                maximum=MAX_MOVEMENT_DURATION,
            )
    elif object_type == "collectible":
        _integer(
            item.get("value"),
            f"{path}.value",
            errors,
            minimum=1,
            maximum=MAX_COLLECTIBLE_VALUE,
        )
    elif object_type in {"door", "goal"} and "requirements" in item:
        _requirements(item.get("requirements"), f"{path}.requirements", errors)


def _aabb_contains_xz(item: dict[str, Any], point: list[float]) -> bool:
    transform = item.get("transform")
    size = item.get("size")
    if not isinstance(transform, dict) or not isinstance(size, list) or len(size) != 3:
        return False
    position = transform.get("position")
    if not isinstance(position, list) or len(position) != 3:
        return False
    if not all(is_number(value) for value in position + size + point):
        return False
    return (
        abs(point[0] - position[0]) <= size[0] / 2 + 0.05
        and abs(point[2] - position[2]) <= size[2] / 2 + 0.05
    )


def _support_below(
    objects: list[dict[str, Any]], point: list[float], max_drop: float
) -> bool:
    for item in objects:
        if item.get("type") not in {"static_box", "ramp", "moving_platform"}:
            continue
        if not _aabb_contains_xz(item, point):
            continue
        position = item["transform"]["position"]
        size = item["size"]
        top = position[1] + size[1] / 2
        drop = point[1] - top
        if -0.25 <= drop <= max_drop:
            return True
    return False


def _inside_aabb(item: dict[str, Any], point: list[float]) -> bool:
    transform = item.get("transform")
    size = item.get("size")
    if not isinstance(transform, dict) or not isinstance(size, list) or len(size) != 3:
        return False
    position = transform.get("position")
    if not isinstance(position, list) or len(position) != 3:
        return False
    if not all(is_number(value) for value in position + size + point):
        return False
    return all(
        abs(point[axis] - position[axis]) <= size[axis] / 2
        for axis in range(3)
    )


def validate_spec(data: Any) -> list[str]:
    """Return stable, ordered validation errors for a v1 spec."""

    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root: expected a JSON object"]

    _unknown_fields(data, ROOT_FIELDS, "root", errors)
    _require_fields(data, ROOT_FIELDS, "root", errors)
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != SPEC_VERSION:
        errors.append(f"version: expected integer {SPEC_VERSION}")

    _validate_game(data.get("game"), errors)
    _validate_player(data.get("player"), errors)
    _validate_camera(data.get("camera"), errors)
    _validate_spawn(data.get("spawn"), errors)

    raw_objects = data.get("objects")
    if not isinstance(raw_objects, list):
        errors.append("objects: expected an array")
        return errors
    if not raw_objects:
        errors.append("objects: expected at least one object")
    if len(raw_objects) > MAX_OBJECTS:
        errors.append(f"objects: expected at most {MAX_OBJECTS} objects")
    for index, item in enumerate(raw_objects):
        _validate_object(item, index, errors)

    objects = [item for item in raw_objects if isinstance(item, dict)]
    ids: dict[str, tuple[str | None, int]] = {}
    for index, item in enumerate(objects):
        object_id = item.get("id")
        if not isinstance(object_id, str) or not ID_PATTERN.fullmatch(object_id):
            continue
        if object_id in ids:
            errors.append(f"objects[{index}].id: duplicate id {object_id!r}")
        else:
            ids[object_id] = (item.get("type"), index)

    goals = [item for item in objects if item.get("type") == "goal"]
    if not goals:
        errors.append("objects: at least one goal is required")
    solids = [
        item
        for item in objects
        if item.get("type") in {"static_box", "ramp", "moving_platform"}
    ]
    if not solids:
        errors.append("objects: at least one traversable solid is required")

    total_collectibles = 0
    for item in objects:
        if item.get("type") == "collectible":
            value = item.get("value", 1)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                total_collectibles += value
    if total_collectibles > MAX_TOTAL_COLLECTIBLE_VALUE:
        errors.append(
            "objects: total collectible value must be no greater than "
            f"{MAX_TOTAL_COLLECTIBLE_VALUE}"
        )

    for index, item in enumerate(raw_objects):
        if not isinstance(item, dict) or item.get("type") not in {"door", "goal"}:
            continue
        requirements = item.get("requirements")
        if not isinstance(requirements, dict):
            continue
        count = requirements.get("collectibles", 0)
        if (
            isinstance(count, int)
            and not isinstance(count, bool)
            and count > total_collectibles
        ):
            errors.append(
                f"objects[{index}].requirements.collectibles: requires {count}, "
                f"but only {total_collectibles} collectible value exists"
            )
        switches = requirements.get("switches", [])
        if isinstance(switches, list):
            for reference_index, switch_id in enumerate(switches):
                if not isinstance(switch_id, str) or not ID_PATTERN.fullmatch(switch_id):
                    continue
                target = ids.get(switch_id)
                ref_path = f"objects[{index}].requirements.switches[{reference_index}]"
                if target is None:
                    errors.append(f"{ref_path}: unknown object id {switch_id!r}")
                elif target[0] != "switch":
                    errors.append(
                        f"{ref_path}: {switch_id!r} refers to {target[0]!r}, not a switch"
                    )

    spawn = data.get("spawn")
    spawn_position = spawn.get("position") if isinstance(spawn, dict) else None
    if (
        isinstance(spawn_position, list)
        and len(spawn_position) == 3
        and all(is_number(value) for value in spawn_position)
    ):
        if solids and not _support_below(solids, spawn_position, max_drop=5.0):
            errors.append(
                "spawn.position: no traversable solid supports the spawn within a 5-unit drop"
            )
        for index, item in enumerate(raw_objects):
            if (
                isinstance(item, dict)
                and item.get("type") == "hazard"
                and _inside_aabb(item, spawn_position)
            ):
                errors.append(f"spawn.position: starts inside hazard {item.get('id', index)!r}")

    return errors


def normalized_spec(data: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical v1 representation after successful validation."""

    return deepcopy(data)
