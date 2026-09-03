# Game Spec v1

This document is the human authoring reference for the bundled Godot 4 third-person graybox
template. The JSON describes structure and rules, not final appearance. The Python
`scripts/validate_spec.py` validator is the **only normative exact-schema gate**; this reference and
runtime must remain aligned with it. Runtime performs defensive structural checks so malformed data
fails safely, but those checks do not define or replace exact validation. Prose in a prompt never
overrides validated JSON.

Generation records the normalized spec digest and gameplay-file hashes in `build-report.json`.
Verification revalidates the spec and checks that manifest before runtime, ensuring Godot runs the
validated spec and recorded files. After an agent edits a generated project, revalidate the spec and
refresh the manifest, then rerun full verification; refreshing the manifest is not a test pass.

## Coordinate and shape conventions

- Units are Godot meters. `Y` is up; the default forward route points toward negative `Z`.
- Every vector is a JSON array of exactly three finite numbers in `[x, y, z]` order.
- Every `position` and `movement.offset` component has absolute value at most `10000`.
- `rotation_degrees` contains the `Node3D` Euler components `[x, y, z]`, expressed in degrees.
- Every `rotation_degrees` component has absolute value at most `36000`.
- A box's `position` is its center. Its top surface is `position[1] + size[1] / 2`.
- `size` is the full local-axis box size; each component is in `[0.01, 1000]`.
- Colors use `#RRGGBB` or `#RRGGBBAA`. Alpha is useful for trigger volumes.
- Geometry is intentionally coarse. A `ramp` is a rotated box, not a wedge or arbitrary mesh.

## Exact root contract

The root object has exactly these keys:

```json
{
  "version": 1,
  "game": {
    "title": "Switchback Trial",
    "objective": "Collect both signals, activate the bridge switch, and reach the exit.",
    "completion_message": "Route complete"
  },
  "player": {
    "walk_speed": 5.5,
    "sprint_speed": 9.0,
    "acceleration": 28.0,
    "deceleration": 32.0,
    "air_control": 0.35,
    "turn_speed": 12.0,
    "gravity": 24.0,
    "jump_velocity": 8.5
  },
  "camera": {
    "distance": 6.5,
    "fov": 70.0,
    "initial_pitch_degrees": -10.0
  },
  "spawn": {
    "position": [0.0, 1.2, 5.0],
    "rotation_degrees": [0.0, 0.0, 0.0]
  },
  "objects": []
}
```

Rules:

- `version` is the integer `1`, not the string `"1"` or the float `1.0`.
- All three `game` strings are non-empty after trimming.
- All `player` values are finite numbers. `walk_speed`, `sprint_speed`, and `jump_velocity` are in
  `(0, 100]`; `acceleration`, `deceleration`, `turn_speed`, and `gravity` are in `(0, 500]`;
  `sprint_speed >= walk_speed`; `air_control` is in `[0, 1]`.
- `camera.distance` is in `[0.5, 20]`, `camera.fov` in `[20, 120]`, and
  `camera.initial_pitch_degrees` in `[-45, 45]`.
- `spawn` contains exactly `position` and `rotation_degrees`.
- `objects` is a non-empty array of at most `512` entries with at least one `goal`.
- Unknown keys are invalid. Add a versioned field and matching runtime support instead of hiding
  unsupported behavior in an extra property.

## Common object contract

Every object has these required common keys:

```json
{
  "id": "safe_landing",
  "type": "static_box",
  "transform": {
    "position": [0.0, -0.5, 2.0],
    "rotation_degrees": [0.0, 0.0, 0.0]
  },
  "size": [8.0, 1.0, 12.0],
  "color": "#8D96A1"
}
```

- `id` is 1–64 characters matching `^[a-z][a-z0-9_]{0,63}$` and is unique across the spec.
- `type` is one of the nine types below.
- `transform` contains exactly `position` and `rotation_degrees`.
- Use stable semantic IDs such as `atrium_switch`, not array positions such as `object_17`.
- Type-specific keys are allowed only where this document declares them.

## Supported object types

### `static_box`

A visible solid box with collision. It is used for floors, walls, columns, steps, and platforms.
It has no type-specific keys.

### `ramp`

A visible solid rotated box with collision. Pitch it around `X` for a route along `Z`, or around
`Z` for a route along `X`. It has no type-specific keys. Because it is still a box, check both
ends for protruding edges and unintended underside collision.

### `moving_platform`

A solid `AnimatableBody3D` that continuously travels from its transform position to
`position + movement.offset`, then returns along the same line.

```json
{
  "id": "bridge_shuttle",
  "type": "moving_platform",
  "transform": {
    "position": [0.0, 1.5, -18.0],
    "rotation_degrees": [0.0, 0.0, 0.0]
  },
  "size": [3.0, 0.6, 3.0],
  "color": "#E3B958",
  "movement": {
    "offset": [0.0, 0.0, -5.0],
    "duration": 2.5
  }
}
```

`movement` contains exactly `offset` and `duration`. The offset must be non-zero and obey the
component bounds above. `duration` is in `[0.05, 3600]` seconds and is the one-way travel time, so a
full out-and-back cycle is twice that value.
Rotation does not rotate the movement vector; the offset is in world axes.

### `hazard`

A visible trigger volume. Player contact immediately respawns the player at `spawn`. It does not
provide a supporting surface and has no health, damage-over-time, or checkpoint behavior. It has
no type-specific keys.

### `collectible`

A visible trigger that disappears after the player touches it and adds `value` to the run's scalar
collectible total.

```json
{
  "id": "signal_a",
  "type": "collectible",
  "transform": {
    "position": [0.0, 1.0, -8.0],
    "rotation_degrees": [0.0, 0.0, 0.0]
  },
  "size": [0.7, 0.7, 0.7],
  "color": "#62E6FF",
  "value": 1
}
```

`value` is an integer in `[1, 1000]`, and the sum across all collectibles is at most `10000`. This
is one undifferentiated counter; named keys, inventory slots, consumption, and item-specific door
requirements are not supported.

### `switch`

A visible trigger. Touching it activates it permanently for the current run. Requirements refer to
switches by their object IDs. A switch cannot toggle off, time out, require another object, or be
operated remotely. It has no type-specific keys.

### `door`

A visible solid blocker. It opens and stops blocking when all declared requirements are met.
Omitting `requirements` means the door is immediately open and is usually a design mistake.

```json
{
  "id": "exit_door",
  "type": "door",
  "transform": {
    "position": [0.0, 1.5, -25.0],
    "rotation_degrees": [0.0, 0.0, 0.0]
  },
  "size": [5.0, 3.0, 0.5],
  "color": "#D27B64",
  "requirements": {
    "collectibles": 2,
    "switches": ["atrium_switch"]
  }
}
```

### `goal`

A visible trigger volume. Touching an unlocked goal completes the run and displays
`game.completion_message`. A locked goal does not complete the run. Its optional `requirements`
has the same contract as a door.

### `marker`

A visible, non-colliding orientation or route landmark. It has no interaction, label, trigger, or
game-state effect. It has no type-specific keys.

## Requirements contract

Only `door` and `goal` may contain `requirements`:

```json
{
  "collectibles": 0,
  "switches": []
}
```

- The object contains exactly these two keys.
- `collectibles` is an integer in `[0, 10000]` and means the required accumulated value, not the
  number of collectible objects.
- `switches` is an array of at most `128` unique IDs. Every referenced ID must exist and have type
  `switch`.
- Both conditions are conjunctive: the collectible total must be high enough and every listed
  switch must be active.
- Empty requirements unlock immediately.

The total collectible requirement of any reachable gate must not exceed the sum of collectible
values that can be reached before that gate. Required switches must also be reachable before the
gate. This dependency property cannot be proven from JSON types alone and is a mandatory design
review item.

## Deliberately unsupported in v1

The template does not implement combat, enemies or AI, health, checkpoints, lives, vehicles,
multiplayer, crouch, climbing, dash, physics-object puzzles, arbitrary meshes, scripted cameras,
branching dialogue, item types, consumable keys, timed or toggle switches, moving hazards, or
multiple levels. Textures, final materials, animation, audio, depth, normals, optical flow, and
video rendering also remain outside this graybox stage.

If a prompt requires one of these, either reduce it to the closest supported structural loop with
the user's intent preserved, or stop the ordinary generation call and scope a separate skill/template
extension. The extension is not complete until its versioned schema, Python validator, generator,
runtime, focused behavior test, and this reference agree.
