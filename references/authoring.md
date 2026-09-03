# Prompt-to-Spec Authoring Guide

Use this guide after reading `game-spec.md`. The goal is a short, completable third-person graybox
route whose mechanics are encoded in the canonical JSON, not implied by commentary.
`scripts/validate_spec.py` is the only normative exact-schema gate; this guide supplies design
judgment and does not authorize fields or values the validator rejects.

## 1. Establish the acceptance contract

Translate the prompt into these facts before placing geometry:

1. **Primary verb:** running, jumping, riding, collecting, or activating.
2. **Loop:** what the player repeatedly observes, decides, and does.
3. **Route beats:** safe start, teaching beat, escalation, final test, and goal.
4. **Failure:** v1 hazards and falling reset to the single spawn; there are no checkpoints or lives.
5. **Win:** physical goal contact plus any collectible and switch requirements.
6. **Camera feel:** follow distance, FOV, pitch, corridor clearance, and opening sightline.
7. **Exclusions:** prompt details deliberately omitted because v1 does not implement them.

Ask the user only when a missing choice would materially change the game. Otherwise select the
smallest supported interpretation and put the assumption in the human-readable delivery report,
not in an undeclared JSON field or machine `build-report.json` manifest.

If the central loop depends on an unsupported capability, stop and say exactly what runtime
component is missing. Do not relabel a marker as an enemy, describe a static door as locked, or
claim a decorative box is an implemented mechanic.
Implement it only as an explicitly scoped skill/template schema extension—validator, generator,
runtime, reference, and focused test together—not as improvisation inside a normal generation call.

## 2. Choose conservative tuning

Start from the tested baseline unless the prompt explicitly calls for a different feel:

```json
{
  "walk_speed": 5.5,
  "sprint_speed": 9.0,
  "acceleration": 28.0,
  "deceleration": 32.0,
  "air_control": 0.35,
  "turn_speed": 12.0,
  "gravity": 24.0,
  "jump_velocity": 8.5
}
```

```json
{
  "distance": 6.5,
  "fov": 70.0,
  "initial_pitch_degrees": -10.0
}
```

For a more deliberate corridor, lower walk and sprint speeds without weakening acceleration so
the controller remains responsive. For a broad obstacle course, modestly increase camera distance
or FOV. Change one feel dimension at a time; geometry and movement tuning are coupled.

Stay well within the hard validator budgets: at most 512 objects; position/offset components within
±10000; rotations within ±36000 degrees; size components from 0.01 to 1000; moving durations from
0.05 to 3600 seconds; walk/sprint/jump at most 100; and acceleration/deceleration/turn/gravity at
most 500. Each collectible value is at most 1000, their total at most 10000, each collectible
requirement at most 10000, and a requirement names at most 128 switches. These are safety ceilings,
not recommended design targets.

## 3. Design state dependencies before coordinates

Write a tiny dependency plan such as:

```text
spawn -> signal_a -> atrium_switch -> exit_door -> goal
             \-> signal_b -----------/
```

Then enforce these invariants:

- Every required collectible and switch is physically reachable before the door or goal that
  requires it.
- A door never blocks its own prerequisite.
- The collectible threshold is no greater than the reachable sum of `value` fields.
- An optional branch rejoins the primary route; the player cannot finish in a sealed pocket.
- There is at least one goal and at least one finite route from spawn to an unlocked goal.
- Requirements encode actual state. Visual ordering or nearby markers never count as a lock.

Use one gate to teach one dependency before combining collectible and switch requirements in a
later gate. A short whitebox benefits more from a readable state graph than from object count.

## 4. Lay out the route from macro to micro

Place objects in this order:

1. A broad start floor under the spawn, with two to three seconds of safe movement.
2. Large route masses and walls that make the intended direction readable from the opening camera.
3. Landing surfaces and ramps for each height change.
4. Hazards below or beside failure gaps, covering the entire plausible fall region.
5. Moving-platform endpoints, each with a safe wait and landing surface.
6. Collectibles, switches, doors, and their prerequisite-safe ordering.
7. The goal, then markers only where silhouette or direction still needs help.

Keep floor and wall geometry separate. Avoid coplanar duplicate boxes, paper-thin floors, enclosed
spawns, and a ceiling directly behind the camera. Use whole meters for macro layout and decimals
only for deliberate surface alignment.

### Spawn clearance

The player proxy is approximately a 0.8 m wide, 1.8 m high capsule. A conservative spawn has:

- at least 0.5 m horizontal clearance around the capsule;
- at least 2.2 m free vertical space;
- a solid floor slightly below the capsule center;
- no hazard or interaction trigger intersecting the capsule;
- a visible first route beat along the initial camera view.

### Jump budget

For gravity `g` and jump velocity `v`, use these estimates:

```text
peak_height = v² / (2g)
same_level_airtime = 2v / g
ideal_horizontal_distance = sprint_speed * same_level_airtime
```

The ideal distance assumes immediate full speed and perfect timing. It is not a design target.
Keep required same-height gap crossings at or below roughly 55% of that distance and required
upward landings at or below roughly 60% of peak height until an interactive play-test supports a
harder value. Make the first landing at least 2 m wide; narrow surfaces belong later in the route.

At the baseline, peak height is about 1.5 m and ideal same-level horizontal distance is about
6.4 m. Treat roughly 3.5 m horizontal and 0.9 m upward as conservative required maxima, then test.

### Ramps and moving platforms

- Prefer ramp slopes below the controller's 50-degree floor limit, with flush entry and exit.
- Remember that a ramp is a rotated rectangular box; inspect its lower end for a blocking lip.
- A moving platform's `offset` is a world-space line segment. Ensure both endpoints have reachable
  waiting/landing zones and the platform cannot carry the player into a wall.
- Start with a 2 to 4 second one-way duration. Very fast or tiny shuttles require explicit testing.
- Do not require a blind leap to a platform that begins outside the camera's useful view.

### Hazards and reset

Hazards are trigger volumes, not collision floors. Place them high enough and wide enough to catch
falls before the generic out-of-bounds reset. Confirm that reset returns the player to an unoccupied
spawn with zero velocity and a snapped camera. Avoid unavoidable spawn-to-hazard chains.

## 5. Compose for the third-person camera

The orbit camera uses a collision-aware spring arm, but collision avoidance is not a substitute for
camera space.

- Keep the primary path visible at the default pitch without requiring immediate mouse input.
- Give narrow corridors more width than the player alone needs; approximately 4 to 6 m supports a
  6.5 m boom better than a shoulder-width tunnel.
- Avoid low ceilings, walls immediately behind the player, and 180-degree reversals in small rooms.
- Use large massing changes and contrasting flat colors for route beats; do not depend on texture.
- Put a marker outside the path only as a silhouette cue. It cannot display instructions.
- Check camera collision at walls, under ramps, on moving platforms, and when backtracking.

## 6. Encode the spec, then review it as data

Use exact canonical fields from `game-spec.md`. Keep IDs stable and dependency-oriented. Before
generation, inspect:

- duplicate or malformed IDs;
- non-finite, zero, or negative sizes;
- unsupported or misspelled types;
- missing type-specific fields;
- bad switch references or impossible collectible totals;
- geometry intersections that trap the player;
- spawn-to-goal dependency ordering;
- required jumps beyond the conservative movement budget;
- doors that can be bypassed around their sides or over their top.

The static validator catches the first four classes and reference errors. It cannot prove spatial
reachability, camera readability, or that a blocker actually seals a passage. Those remain explicit
review and play-test obligations.

For later coding-agent changes within v1, prefer editing the source spec, validating it, and
regenerating into a fresh directory. A necessary direct GDScript edit invalidates the manifest:
revalidate `data/game_spec.json`, run `scripts/refresh_manifest.py --project ... --reason ...`, then
run full verification. Manifest refresh records current hashes; it does not prove behavior or pass
any quality gate.

## 7. Scope translation examples

- “Collect three energy cells to open the exit” maps directly to three `collectible` objects and a
  `door` or `goal` whose `requirements.collectibles` is `3`.
- “Press two floor buttons to extend a bridge” maps to two permanent `switch` triggers and a door
  that disappears when both are active. It does **not** create an animated extending bridge.
- “Avoid lava while riding an elevator” maps to a `hazard` and a vertical `moving_platform` if both
  endpoints are safe and visible.
- “A guard chases the player” is unsupported because there is no agent, perception, chase, damage,
  or health component. A static red marker is not an acceptable substitute.
- “Use a key on a matching lock” can be reduced to the scalar collectible counter only if item
  identity is irrelevant. Otherwise it requires a tested template extension.

When reducing a prompt, preserve the actual player decision and disclose the reduction. When the
reduction destroys the central verb, stop rather than shipping a misleading prototype.
