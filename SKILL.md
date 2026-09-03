---
name: prompt-to-godot-graybox
description: Generate and quality-gate a runnable Godot 4 third-person graybox prototype from a concise gameplay prompt. Use for corridor games, platforming routes, obstacle courses, traversal puzzles, moving platforms, hazards, collectibles, switches, doors, and goals. Do not use for finished art, multiplayer, vehicles, or combat-heavy games unless the template is explicitly extended and tested first.
---

# Prompt to Godot Graybox

Turn the user's gameplay intent into a small, data-driven Godot project that can be opened, played,
and edited by another coding agent. The deliverable is a structural whitebox: geometry, collision,
movement, camera, route, and game-state logic. Do not add textures or pretend this produces final art.

## Fixed contract

- Target Godot 4.7.2 or newer using the compatibility renderer and no external assets.
- Keep the third-person controller, orbit camera, collision, reset flow, HUD, and data-driven world.
- Use only mechanics implemented by the bundled template. Read `references/game-spec.md` before
  writing a spec.
- Treat unsupported mechanics as a separate skill/template extension: version the schema, update
  the Python validator, runtime, generator, reference, and focused behavior test together. Do not
  improvise that extension during an ordinary generation call or claim prose/decorations implement it.
- Keep all generated-project edits inside the requested output directory. Never overwrite a
  non-empty directory implicitly.
- Treat `validate_spec.py` as the only normative exact-schema gate. Runtime checks are defensive;
  the build-report manifest binds the validated spec and generated files used by verification.

## Workflow

Set `SKILL_ROOT` to the absolute directory containing this `SKILL.md` before running commands.

### 1. Translate the prompt into an acceptance contract

Read `references/authoring.md`. Extract:

- player verb and moment-to-moment loop;
- start, route beats, failure/reset behavior, and explicit win condition;
- required objects and their dependency graph;
- camera and movement feel;
- user-requested constraints and deliberately excluded scope.

Ask a question only when one missing answer would materially change the game. Otherwise choose the
smallest playable interpretation and record assumptions in the delivery report.

### 2. Author and validate the spec

Write a version-1 JSON spec in the generated work area. Use stable, descriptive IDs and whole
meters unless a smaller value is intentional. Build from macro route to individual objects:

1. spawn and safe opening platform;
2. primary path and readable boundaries;
3. challenge beats with recoverable difficulty progression;
4. mechanic dependencies such as collectible or switch targets;
5. goal and completion requirement.

Validate before generating code:

```bash
python3 "$SKILL_ROOT/scripts/validate_spec.py" game-spec.json
```

Validation failure blocks generation. Fix the spec; do not patch around the validator.

### 3. Generate the project

```bash
python3 "$SKILL_ROOT/scripts/new_project.py" \
  --spec game-spec.json \
  --output ./generated-game
```

The generator copies the tested template, preserves the validated source spec byte-for-byte, writes
derived runtime data and a build report, and leaves
ordinary Godot/GDScript files available for later coding-agent edits. Do not hand-copy the template.

### Coding-agent edits after generation

For any supported v1 layout, tuning, text, or requirement change, edit the source spec, validate it,
and regenerate into a fresh directory. This is the preferred and reproducible edit path.

If a focused GDScript/template edit is genuinely required, make the smallest change, revalidate
`data/game_spec.json`, then refresh the machine manifest before full verification:

```bash
python3 "$SKILL_ROOT/scripts/refresh_manifest.py" \
  --project ./generated-game \
  --reason "describe the focused coding-agent edit"
python3 "$SKILL_ROOT/scripts/verify_project.py" \
  --project ./generated-game \
  --godot /absolute/path/to/godot
```

Manifest refresh only records current validated inputs and file hashes; it is not a pass and cannot
replace runtime/mechanic verification. Never refresh around a validation failure.

### 4. Verify, then play-test

Read `references/quality-gates.md`. Locate Godot with `command -v godot` or use a user-provided
binary. Run the mandatory verifier:

```bash
python3 "$SKILL_ROOT/scripts/verify_project.py" \
  --project ./generated-game \
  --godot "$(command -v godot)"
```

Passing static checks alone is not proof of playability. A missing Godot executable is `BLOCKED`,
not `PASS`; `--static-only` is diagnostic and must be reported as incomplete verification.
The full verifier uses a fresh isolated copy, runs headless import only to prepare its class/resource
cache, then performs the headless load/runtime test; import by itself is never playability evidence.
Full verification must enforce exactly one `MECHANIC <name> PASS count=<n>` or
`MECHANIC <name> N/A count=0` line for each of the nine mechanic rows in the quality gates; a
summary marker without that complete, spec-count-matched evidence fails.

When a display is available, also run the project and inspect the opening view, route readability,
camera collision, each mechanic, reset, and completion. A headless pass proves scripted behavior,
not subjective level feel.

### 5. Use a bounded correction loop

For each failed gate, choose exactly one root cause:

- `spec`: layout, reference, dependency, reachability, or acceptance-contract defect;
- `template`: runtime component or controller defect;
- `environment`: Godot unavailable or unable to launch.

Change one cause group, rerun validation, regenerate into a fresh empty directory, and rerun the full
verification. Limit automatic correction to three iterations. Stop early on repeated defects,
oscillation, or an environment blocker; report the evidence and request input instead of looping
indefinitely.

## Completion standard

Completion requires all mandatory gates to pass and the result to contain:

- `project.godot` and a runnable main scene;
- `data/game_spec.json`, preserving the source of truth;
- editable GDScript and JSON with no binary gameplay dependency;
- `build-report.json`, the machine integrity manifest identifying versions, digests, and file hashes;
- verifier evidence showing Godot exit code zero, complete per-mechanic evidence, and the expected
  pass marker.

Separately write a human delivery report with the project path, exact launch command, controls,
implemented loop, verification result, assumptions, and remaining feel/art limitations. Do not put
human claims in or confuse them with `build-report.json`. Say `generated and verified`, not
`finished game`; final visuals belong to the downstream rendering stage.
