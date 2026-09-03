# Prompt to Godot Graybox

A Codex skill that turns a concise gameplay prompt into a runnable, data-driven Godot 4
third-person graybox project and verifies the generated result.

The skill is designed for small corridor games, traversal challenges, obstacle courses,
collectibles, switches, doors, goals, hazards, ramps, and moving platforms. It deliberately
produces structural whitebox geometry rather than final art.

## What it provides

- A Godot 4.7.2+ compatibility-renderer template with a third-person controller and orbit camera.
- A strict versioned JSON schema for data-driven level construction.
- Collectibles, permanent switches, requirement-driven doors and goals, hazards, ramps, and moving
  platforms.
- Python tooling for spec validation, reproducible generation, manifest refresh, and full project
  verification.
- Headless Godot behavior tests with exact per-mechanic evidence.
- Quality gates for route design, camera readability, play-testing, and bounded correction.

## Requirements

- Python 3.10 or newer.
- Godot 4.7.2 or newer for full runtime verification.
- No external gameplay assets or Python packages are required.

## Install as a Codex skill

Clone the repository into your Codex skills directory:

```bash
git clone https://github.com/deeptimhe/prompt-to-godot-graybox.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/prompt-to-godot-graybox"
```

Restart Codex after installation. The skill can then be invoked as:

```text
$prompt-to-godot-graybox Generate a third-person corridor game where ...
```

## Generate a project directly

Create and validate a version-1 spec by following `references/game-spec.md`, then run:

```bash
python3 scripts/validate_spec.py game-spec.json
python3 scripts/new_project.py --spec game-spec.json --output ./generated-game
python3 scripts/verify_project.py \
  --project ./generated-game \
  --godot "$(command -v godot)"
```

The output remains an ordinary editable Godot project. Its validated source spec is preserved
byte-for-byte at `data/game_spec.json`, and `build-report.json` binds that spec to the generated
gameplay files used by verification.

## Supported schema v1 mechanics

- Static boxes and rotated-box ramps
- Linearly moving platforms
- Respawn hazards
- Scalar-value collectibles
- Permanent floor switches
- Doors and goals with conjunctive collectible/switch requirements
- Non-interactive route markers

Combat, enemies, checkpoints, vehicles, multiplayer, item-specific inventory, timed switches,
textures, audio, and final art are intentionally outside schema v1.

## Development and testing

Run the Python tooling tests:

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
```

Validate the bundled fixtures:

```bash
python3 scripts/validate_spec.py scripts/fixtures/sprint_course.json
python3 scripts/validate_spec.py scripts/fixtures/switch_vault.json
```

For a full end-to-end check, generate a fixture and pass the resulting project to
`scripts/verify_project.py` with an explicit Godot executable.

## Repository layout

```text
SKILL.md                 Codex workflow and completion contract
agents/openai.yaml       Skill display metadata
assets/godot-template/   Generated-project template and Godot behavior tests
references/              Authoring guide, exact schema, and quality gates
scripts/                 Validator, generator, verifier, manifest tooling, and tests
```

## Contributing

Keep schema, validator, generator, runtime, reference documentation, and focused behavior tests in
sync. New mechanics require a versioned schema change and runtime/test coverage; prose-only or
decorative substitutes are not accepted.

Run the complete local test suite before opening a pull request.

## License

MIT. See [LICENSE](LICENSE).
