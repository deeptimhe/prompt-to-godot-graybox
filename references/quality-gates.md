# Quality Gates and Correction Loop

These gates define what evidence is required before calling a generated project playable. A claim
without its listed evidence fails closed. Run gates in order; a failure blocks later completion.

## Status vocabulary

- `PASS`: the gate's command or review completed and its evidence is available.
- `FAIL`: the gate ran and found a reproducible defect.
- `BLOCKED`: the gate could not run because a required tool or display was unavailable.
- `NOT RUN`: no claim can be made for the gate.

Do not convert `BLOCKED` or `NOT RUN` to `PASS`, average a failed gate into an overall pass, or use
static validation as evidence of runtime playability.

## G0 — Acceptance and scope

Pass only when the delivery report names:

- primary verb and minute-to-minute loop;
- spawn, ordered route beats, failure/reset behavior, and win condition;
- all prompt assumptions and scope reductions;
- requested mechanics that v1 deliberately does not implement.

Fail when the design relies on prose-only mechanics or uses a decorative object to impersonate an
unsupported runtime behavior.

## G1 — Canonical spec

Run:

```bash
python3 "$SKILL_ROOT/scripts/validate_spec.py" game-spec.json
```

Required evidence is exit code zero and the validator's success marker. Review the full diagnostic
list on failure rather than fixing only its first line.

This Python validator is the only normative exact-schema gate. Runtime schema checks are defensive
and cannot substitute for this command. Hard limits include 512 objects; position/offset components
within ±10000; rotation components within ±36000; size components in `[0.01, 1000]`; moving duration
in `[0.05, 3600]`; the player bounds in `game-spec.md`; collectible value/total limits of
1000/10000; collectible requirements at most 10000; and at most 128 required switches.

In addition to schema validation, a reviewer must confirm:

- all door and goal switch IDs resolve to switch objects;
- collectible thresholds do not exceed collectible value reachable before the gate;
- prerequisites are not placed behind the object they unlock;
- spawn has a supporting surface and the route contains at least one goal;
- required gaps and rises fit the conservative jump budget;
- hazards cover intended failure regions without overlapping spawn;
- doors physically block the intended passage while closed.

The last six are design checks. A parser success marker alone does not pass them.

## G2 — Reproducible generation

Generate into a new empty directory. Pass only when:

- the generator exits zero without overwriting an existing non-empty directory;
- `project.godot` and its configured main scene exist;
- `data/game_spec.json` exactly preserves the validated source spec;
- machine `build-report.json` records schema/template versions, the validated source-spec digest,
  and generated gameplay-file hashes;
- reproducible root `.godot/` import caches and regular `.DS_Store` metadata are excluded from the
  manifest; nested directories named `.godot` remain ordinary manifested project content;
- the project contains editable JSON and GDScript and needs no downloaded gameplay asset;
- a second generation from the same spec produces the same gameplay files, excluding documented
  timestamps or evidence paths.

Never repair only the generated copy and call the generator fixed. Correct the source spec or
template, regenerate into a fresh directory, and compare again.

If a coding agent must make a focused direct GDScript edit, first revalidate the embedded spec,
then run `refresh_manifest.py --project ... --reason ...`, and rerun full verification. Refresh is
only a machine integrity snapshot; it is not behavioral evidence or a gate pass. The separate human
delivery report contains assumptions, commands, results, and limitations—not manifest hashes.

## G3 — Fresh headless import, load, and runtime marker

Run the skill verifier with an explicit Godot 4 executable:

```bash
python3 "$SKILL_ROOT/scripts/verify_project.py" \
  --project ./generated-game \
  --godot /absolute/path/to/godot
```

Required evidence:

- verifier exit code zero;
- Godot process exit code zero;
- the expected runtime pass marker;
- no GDScript parse error, missing resource, invalid-node error, or unhandled runtime error;
- report identifies the Godot version and project path tested.

A missing executable is `BLOCKED`. `--static-only` is a useful diagnostic but does not pass this
gate. On a fresh isolated project copy, the verifier first runs Godot's headless `--import` as a
class-cache/resource preflight, then headlessly loads and executes runtime validation. That import
is a prerequisite inside this gate, not independent evidence of playability. Running a different
project, merely opening the editor, or seeing exit zero without the runtime marker is insufficient.

On managed macOS, only exact known environment diagnostics for `user://` logging, editor settings,
or system CA certificates may be allowlisted. The allowlist is environment-level and narrow: it
must never suppress project parse errors, script errors, missing/invalid resources, or node/runtime
errors.

## G4 — Mechanic behavior

The runtime test must exercise the mechanics present in the spec, not only load the main scene. The
verifier must require exactly one `MECHANIC <name> PASS count=<n>` or
`MECHANIC <name> N/A count=0` line for every row below. A missing, duplicate, unknown, malformed,
count-mismatched, or contradictory line fails G4 even if the summary marker is present.

| Mechanic | Required observation |
|---|---|
| controller | movement changes horizontal position; jump produces upward motion and returns to a floor |
| camera | camera follows the player; spring arm has collision enabled; configured distance/FOV/pitch are applied |
| hazard | player contact resets position and velocity to the canonical spawn |
| moving platform | it reaches both configured endpoints and reverses without losing collision |
| collectible | contact adds its positive value exactly once and hides/disables that collectible |
| switch | contact activates it once and it remains active during the run |
| door | it blocks before requirements and opens only after all collectible and switch requirements |
| goal | it refuses completion while locked and completes exactly once when unlocked |
| restart | run state, collectibles, switches, doors, goal state, timer, player, world, and HUD status return to initial values |

`controller`, `camera`, and `restart` must be `PASS count=1`. Each other count must equal the number
of matching objects in the validated spec; it is `PASS` when positive and `N/A` only when zero.
Do not silently omit an applicable row. One component's pass cannot stand in for another's
behavior, and the verifier—not a human summary—must enforce the complete PASS/N/A count set.

## G5 — Route and camera play-test

Automated behavior tests do not prove that a human can read or complete the route. With a display,
launch the project and play from spawn to completion using the documented controls. Verify:

- the opening frame communicates the first direction and challenge;
- the player cannot start intersecting geometry, falling, or triggering state;
- every required jump, ramp, moving platform, collectible, and switch is reachable;
- closed doors cannot be bypassed and open doors do not leave invisible collision;
- hazards reset cleanly without a death loop or lost required progress state;
- the camera does not spend sustained time inside geometry or fully blocked at required beats;
- the goal is clearly visible or discoverable and completion occurs only under its requirements;
- reset and full restart are both understandable from the HUD and controls.

Record the play-test route, result, and any subjective limitation. If no display is available, this
gate is `BLOCKED`; report “generated and runtime-verified; interactive route feel not confirmed,”
not “fully play-tested” or “perfect.”

## G6 — Independent strict review

Use a fresh reviewer agent or person who did not author the current attempt. Give the reviewer the
prompt, spec, generated project, gate evidence, and this checklist. The reviewer must independently
return one of:

- `PASS`, citing evidence for G0 through G5; or
- `FAIL`, naming the earliest failing gate, exact reproduction step, expected result, actual result,
  and smallest likely root-cause group.

The author cannot overrule the reviewer with an unsupported assertion. A reviewer may pass a
display-blocked build only as `runtime-verified`, never as interactively play-tested.

## Evidence-based correction loop

Use at most three correction attempts after the initial failed evaluation. Keep a small attempt log:

```text
attempt: 1
failing_gate: G4
evidence: exit code 1; door opened after only one of two required switches
root_cause: template
change: require all switch IDs before calling open()
result: pending
```

For each attempt:

1. Select the earliest failing gate.
2. Reproduce it and capture the command, exit code, and relevant output or visual observation.
3. Classify exactly one primary root cause: `spec`, `template`, or `environment`.
4. Change the smallest cause group that explains the evidence.
5. Rerun spec validation.
6. Regenerate into a fresh empty directory.
7. Rerun G2 through the failed gate, then all later mandatory gates.
8. Ask the independent reviewer to evaluate the new evidence.

Stop before three attempts if:

- the same failure signature appears twice after a claimed fix;
- fixes oscillate between two states;
- the blocker is environmental and no in-scope remedy exists;
- the next fix requires an unsupported mechanic or materially changes the user's loop.

After the third failed correction, stop and report the remaining defect and evidence. Never loop
indefinitely, silently relax the acceptance contract, or declare success because the attempt limit
was reached.

## Completion language

Use the strongest statement supported by evidence:

- G0–G6 pass: `generated, runtime-verified, and interactively play-tested`.
- G0–G4 pass while G5 is blocked: `generated and runtime-verified; interactive play-test blocked`.
- Only G0–G2 pass: `generated; Godot runtime verification blocked or failed`.
- Any earlier gate fails: `not complete`, followed by the earliest failing evidence.

Always include the generated project path, exact launch command, controls, implemented loop,
verification command/result, assumptions, and remaining whitebox limitations. “Perfect,” “finished
game,” and “final visuals” are never justified by this structural stage.
These belong in the human delivery report; `build-report.json` remains the machine integrity
manifest and must not be edited to contain narrative claims.
