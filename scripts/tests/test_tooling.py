from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
FIXTURES = SCRIPTS / "fixtures"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import new_project  # noqa: E402
import refresh_manifest  # noqa: E402
import validate_spec  # noqa: E402
import verify_project  # noqa: E402
from spec_lib import validate_spec as validate_data  # noqa: E402


def load_fixture(name: str = "switch_vault.json") -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_template(root: Path) -> Path:
    template = root / "template"
    (template / "scripts").mkdir(parents=True)
    (template / "tests").mkdir(parents=True)
    (template / "project.godot").write_text(
        '; generated test template\n[application]\nconfig/name="Template"\n'
        'run/main_scene="res://main.tscn"\n',
        encoding="utf-8",
    )
    (template / "main.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
    (template / "scripts" / "runtime.gd").write_text("extends Node\n", encoding="utf-8")
    (template / "tests" / "validate_project.gd").write_text(
        "extends SceneTree\n", encoding="utf-8"
    )
    return template


def mechanic_output(spec: dict, *, marker: bool = True) -> str:
    expected = verify_project._expected_mechanics(spec)
    lines = [
        f"MECHANIC {name} {status} count={count}"
        for name, (status, count) in expected.items()
    ]
    if marker:
        lines.append(verify_project.EXPECTED_PASS_MARKER)
    return "\n".join(lines) + "\n"


class SpecValidationTests(unittest.TestCase):
    def test_fixtures_are_valid(self) -> None:
        for fixture in sorted(FIXTURES.glob("*.json")):
            with self.subTest(fixture=fixture.name):
                self.assertEqual([], validate_data(load_fixture(fixture.name)))

    def test_fail_closed_and_cross_references(self) -> None:
        spec = load_fixture()
        spec["combat"] = {"enabled": True}
        spec["objects"][4]["requirements"]["switches"] = ["shard_a"]
        spec["objects"][5]["requirements"]["collectibles"] = 99
        errors = validate_data(spec)
        joined = "\n".join(errors)
        self.assertIn("unsupported capability", joined)
        self.assertIn("not a switch", joined)
        self.assertIn("only 2 collectible value exists", joined)

    def test_duplicate_id_and_unsupported_type(self) -> None:
        spec = load_fixture("sprint_course.json")
        spec["objects"][1]["id"] = "start_floor"
        spec["objects"][2]["type"] = "enemy"
        errors = "\n".join(validate_data(spec))
        self.assertIn("duplicate id", errors)
        self.assertIn("unsupported object type", errors)

    def test_collectible_value_is_required(self) -> None:
        spec = load_fixture()
        del spec["objects"][1]["value"]
        self.assertIn(
            "objects[1].value: required field is missing",
            validate_data(spec),
        )

    def test_spawn_must_be_supported_and_safe(self) -> None:
        spec = load_fixture("sprint_course.json")
        spec["spawn"]["position"] = [100.0, 100.0, 100.0]
        self.assertIn("no traversable solid supports", "\n".join(validate_data(spec)))

    def test_validate_cli_json_is_stable(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = validate_spec.main([str(FIXTURES / "sprint_course.json"), "--format", "json"])
        self.assertEqual(0, code)
        payload = json.loads(output.getvalue())
        self.assertEqual("VALID", payload["status"])
        self.assertEqual(5, payload["object_count"])

    def test_practical_numeric_bounds(self) -> None:
        spec = load_fixture("sprint_course.json")
        spec["spawn"]["position"][0] = 10_001
        spec["spawn"]["rotation_degrees"][1] = 36_001
        spec["objects"][0]["size"] = [0.001, 1, 1_001]
        spec["player"]["walk_speed"] = 101
        spec["player"]["sprint_speed"] = 101
        spec["player"]["gravity"] = 501
        errors = "\n".join(validate_data(spec))
        self.assertIn("spawn.position: component absolute values", errors)
        self.assertIn("spawn.rotation_degrees: component absolute values", errors)
        self.assertIn("all components must be at least 0.01", errors)
        self.assertIn("all components must be no greater than 1000", errors)
        self.assertIn("player.walk_speed: expected a number no greater than 100", errors)
        self.assertIn("player.gravity: expected a number no greater than 500", errors)

    def test_movement_collectible_and_requirement_bounds(self) -> None:
        spec = load_fixture("switch_vault.json")
        moving = copy.deepcopy(spec["objects"][0])
        moving["id"] = "moving_probe"
        moving["type"] = "moving_platform"
        moving["movement"] = {"offset": [10_001, 0, 0], "duration": 0.01}
        spec["objects"].append(moving)
        spec["objects"][1]["value"] = 1_001
        spec["objects"][4]["requirements"]["collectibles"] = 10_001
        spec["objects"][4]["requirements"]["switches"] = [
            f"switch_{index}" for index in range(129)
        ]
        errors = "\n".join(validate_data(spec))
        self.assertIn("movement.offset: component absolute values", errors)
        self.assertIn("movement.duration: expected a number at least 0.05", errors)
        self.assertIn("value: expected an integer no greater than 1000", errors)
        self.assertIn("collectibles: expected an integer no greater than 10000", errors)
        self.assertIn("switches: expected at most 128 entries", errors)

    def test_object_count_is_bounded(self) -> None:
        spec = load_fixture("sprint_course.json")
        base = copy.deepcopy(spec["objects"][0])
        while len(spec["objects"]) <= 512:
            item = copy.deepcopy(base)
            item["id"] = f"filler_{len(spec['objects'])}"
            spec["objects"].append(item)
        self.assertIn("objects: expected at most 512 objects", validate_data(spec))


class GenerationTests(unittest.TestCase):
    def test_generation_is_deterministic_and_static_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            first = root / "first"
            second = root / "second"
            arguments = [
                "--spec",
                str(FIXTURES / "switch_vault.json"),
                "--template",
                str(template),
                "--output",
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, new_project.main(arguments + [str(first)]))
                self.assertEqual(0, new_project.main(arguments + [str(second)]))
            first_report = json.loads((first / "build-report.json").read_text(encoding="utf-8"))
            second_report = json.loads((second / "build-report.json").read_text(encoding="utf-8"))
            self.assertEqual(first_report, second_report)
            self.assertEqual(1, first_report["spec_version"])
            self.assertEqual(1, first_report["template_version"])
            self.assertEqual(
                (first / "data" / "game_spec.json").read_bytes(),
                (second / "data" / "game_spec.json").read_bytes(),
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, verify_project.main([str(first), "--static-only"]))

    def test_generation_preserves_source_spec_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            source = root / "source.json"
            source_bytes = json.dumps(
                load_fixture("sprint_course.json"),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            source.write_bytes(source_bytes)
            output = root / "generated"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec",
                            str(source),
                            "--template",
                            str(template),
                            "--output",
                            str(output),
                        ]
                    ),
                )
            self.assertEqual(
                source_bytes,
                (output / "data" / "game_spec.json").read_bytes(),
            )

    def test_nonempty_output_is_refused_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                code = new_project.main(
                    [
                        "--spec",
                        str(FIXTURES / "sprint_course.json"),
                        "--template",
                        str(template),
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(new_project.EXIT_CANT_CREATE, code)
            self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))

    def test_output_cannot_equal_or_be_inside_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            for output in (template, template / "generated-child"):
                with self.subTest(output=output):
                    with contextlib.redirect_stderr(io.StringIO()):
                        code = new_project.main(
                            [
                                "--spec",
                                str(FIXTURES / "sprint_course.json"),
                                "--template",
                                str(template),
                                "--output",
                                str(output),
                            ]
                        )
                    self.assertEqual(new_project.EXIT_CANT_CREATE, code)
                    self.assertFalse((template / "generated-child").exists())

    def test_output_symlink_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            target = root / "empty-target"
            target.mkdir()
            output = root / "output-link"
            output.symlink_to(target, target_is_directory=True)
            with contextlib.redirect_stderr(io.StringIO()):
                code = new_project.main(
                    [
                        "--spec", str(FIXTURES / "sprint_course.json"),
                        "--template", str(template), "--output", str(output),
                    ]
                )
            self.assertEqual(new_project.EXIT_CANT_CREATE, code)
            self.assertTrue(output.is_symlink())
            self.assertEqual([], list(target.iterdir()))

    def test_modified_generated_file_fails_manifest_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec",
                            str(FIXTURES / "sprint_course.json"),
                            "--template",
                            str(template),
                            "--output",
                            str(output),
                        ]
                    ),
                )
            (output / "main.tscn").write_text("changed\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(verify_project.EXIT_FAILED, verify_project.main([str(output), "--static-only"]))

    def test_extra_file_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            for kind in ("extra", "symlink"):
                output = root / kind
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        0,
                        new_project.main(
                            [
                                "--spec",
                                str(FIXTURES / "sprint_course.json"),
                                "--template",
                                str(template),
                                "--output",
                                str(output),
                            ]
                        ),
                    )
                if kind == "extra":
                    (output / "unlisted.txt").write_text("extra", encoding="utf-8")
                else:
                    (output / "linked.txt").symlink_to(output / "main.tscn")
                error_output = io.StringIO()
                with contextlib.redirect_stderr(error_output):
                    self.assertEqual(
                        verify_project.EXIT_FAILED,
                        verify_project.main([str(output), "--static-only"]),
                    )
                if kind == "extra":
                    self.assertIn("unlisted project file", error_output.getvalue())
                else:
                    self.assertIn("symlink is not allowed", error_output.getvalue())

    def test_project_root_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec", str(FIXTURES / "sprint_course.json"),
                            "--template", str(template), "--output", str(output),
                        ]
                    ),
                )
            linked_project = root / "linked-game"
            linked_project.symlink_to(output, target_is_directory=True)
            error_output = io.StringIO()
            with contextlib.redirect_stderr(error_output):
                self.assertEqual(
                    verify_project.EXIT_FAILED,
                    verify_project.main([str(linked_project), "--static-only"]),
                )
            self.assertIn("project path must not be a symlink", error_output.getvalue())

    def test_required_path_type_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec",
                            str(FIXTURES / "sprint_course.json"),
                            "--template",
                            str(template),
                            "--output",
                            str(output),
                        ]
                    ),
                )
            (output / "main.tscn").unlink()
            (output / "main.tscn").mkdir()
            error_output = io.StringIO()
            with contextlib.redirect_stderr(error_output):
                self.assertEqual(
                    verify_project.EXIT_FAILED,
                    verify_project.main([str(output), "--static-only"]),
                )
            self.assertIn("must be a regular file", error_output.getvalue())

    def test_refresh_manifest_accepts_deliberate_safe_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec",
                            str(FIXTURES / "sprint_course.json"),
                            "--template",
                            str(template),
                            "--output",
                            str(output),
                        ]
                    ),
                )
            (output / "scripts" / "runtime.gd").write_text(
                "extends Node\n# deliberate edit\n", encoding="utf-8"
            )
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    verify_project.EXIT_FAILED,
                    verify_project.main([str(output), "--static-only"]),
                )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    refresh_manifest.main(
                        ["--project", str(output), "--reason", "test deliberate edit"]
                    ),
                )
                self.assertEqual(
                    0, verify_project.main([str(output), "--static-only"])
                )
            report = json.loads((output / "build-report.json").read_text(encoding="utf-8"))
            self.assertEqual(2, report["workspace_revision"])
            self.assertEqual(refresh_manifest.REFRESH_ID, report["manifest_source"])
            self.assertEqual("test deliberate edit", report["last_manifest_reason"])

    def test_root_godot_cache_is_ignored_but_nested_name_is_manifested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec", str(FIXTURES / "sprint_course.json"),
                            "--template", str(template), "--output", str(output),
                        ]
                    ),
                )

            (output / ".godot" / "imported").mkdir(parents=True)
            (output / ".godot" / "imported" / "cache.bin").write_bytes(b"cache")
            (output / ".DS_Store").write_bytes(b"host metadata")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0, verify_project.main([str(output), "--static-only"])
                )

            nested = output / "content" / ".godot"
            nested.mkdir(parents=True)
            (nested / "level-fragment.txt").write_text("content\n", encoding="utf-8")
            (nested / ".DS_Store").write_bytes(b"nested host metadata")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    refresh_manifest.main(
                        ["--project", str(output), "--reason", "accept nested content"]
                    ),
                )
                self.assertEqual(
                    0, verify_project.main([str(output), "--static-only"])
                )

            report = json.loads((output / "build-report.json").read_text(encoding="utf-8"))
            paths = set(report["files"])
            self.assertFalse(any(path == ".godot" or path.startswith(".godot/") for path in paths))
            self.assertFalse(any(Path(path).name == ".DS_Store" for path in paths))
            self.assertIn("content/.godot/level-fragment.txt", paths)

    def test_root_godot_cache_symlink_is_rejected_before_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec", str(FIXTURES / "sprint_course.json"),
                            "--template", str(template), "--output", str(output),
                        ]
                    ),
                )
            target = root / "outside-cache"
            target.mkdir()
            (output / ".godot").symlink_to(target, target_is_directory=True)

            for operation in (
                lambda: verify_project.main([str(output), "--static-only"]),
                lambda: refresh_manifest.main(
                    ["--project", str(output), "--reason", "must reject link"]
                ),
            ):
                with self.subTest(operation=operation):
                    errors = io.StringIO()
                    with contextlib.redirect_stderr(errors):
                        self.assertEqual(1, operation())
                    self.assertIn(
                        "symlink is not allowed in project tree: .godot",
                        errors.getvalue(),
                    )

    def test_ds_store_symlink_is_rejected_but_regular_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec", str(FIXTURES / "sprint_course.json"),
                            "--template", str(template), "--output", str(output),
                        ]
                    ),
                )
            metadata = output / ".DS_Store"
            metadata.write_bytes(b"safe metadata")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, verify_project.main([str(output), "--static-only"]))
            metadata.unlink()
            metadata.symlink_to(output / "main.tscn")
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                self.assertEqual(
                    verify_project.EXIT_FAILED,
                    verify_project.main([str(output), "--static-only"]),
                )
            self.assertIn("symlink is not allowed", errors.getvalue())

    def test_refresh_manifest_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec", str(FIXTURES / "sprint_course.json"),
                            "--template", str(template), "--output", str(output),
                        ]
                    ),
                )
            (output / "unsafe-link").symlink_to(output / "main.tscn")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    refresh_manifest.EXIT_FAILED,
                    refresh_manifest.main(
                        ["--project", str(output), "--reason", "should fail"]
                    ),
                )

    def test_missing_godot_is_blocked_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = make_template(root)
            output = root / "game"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    new_project.main(
                        [
                            "--spec",
                            str(FIXTURES / "sprint_course.json"),
                            "--template",
                            str(template),
                            "--output",
                            str(output),
                        ]
                    ),
                )
            original = verify_project._find_godot
            verify_project._find_godot = lambda _explicit: None
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(verify_project.EXIT_BLOCKED, verify_project.main([str(output)]))
            finally:
                verify_project._find_godot = original

    def test_runtime_requires_exact_marker(self) -> None:
        spec = load_fixture("sprint_course.json")
        responses = [
            (0, "4.7.2.stable.official\n"),
            (0, "import ok\n"),
            (0, mechanic_output(spec, marker=False) + "almost pass\n"),
        ]
        with mock.patch.object(verify_project, "_run", side_effect=responses):
            errors, checks, evidence = verify_project._runtime_checks(
                Path("/tmp/example"), Path("/tmp/godot"), spec
            )
        self.assertIn("without exact pass marker", "\n".join(errors))
        self.assertNotIn("behavior", checks)
        self.assertIsNone(evidence["marker"])
        self.assertEqual(0, evidence["exit_code"])

    def test_runtime_rejects_godot_before_4_7_2(self) -> None:
        with mock.patch.object(
            verify_project, "_run", return_value=(0, "4.7.1.stable\n")
        ):
            errors, _checks, evidence = verify_project._runtime_checks(
                Path("/tmp/example"), Path("/tmp/godot"), load_fixture()
            )
        self.assertIn("Godot 4.7.2 or newer", "\n".join(errors))
        self.assertEqual("4.7.1.stable", evidence["godot_version"])

    def test_runtime_rejects_future_major(self) -> None:
        with mock.patch.object(
            verify_project, "_run", return_value=(0, "5.0.0.stable\n")
        ):
            errors, _checks, _evidence = verify_project._runtime_checks(
                Path("/tmp/example"), Path("/tmp/godot"), load_fixture()
            )
        self.assertIn("major version 4", "\n".join(errors))

    def test_runtime_accepts_exact_marker(self) -> None:
        spec = load_fixture("switch_vault.json")
        responses = [
            (0, "4.7.2.stable.official\n"),
            (0, "import ok\n"),
            (0, mechanic_output(spec)),
        ]
        with mock.patch.object(verify_project, "_run", side_effect=responses) as runner:
            errors, checks, evidence = verify_project._runtime_checks(
                Path("/tmp/example"), Path("/tmp/godot"), spec
            )
        self.assertEqual([], errors)
        self.assertIn("behavior", checks)
        self.assertEqual(verify_project.EXPECTED_PASS_MARKER, evidence["marker"])
        self.assertEqual(9, len(evidence["mechanics"]))
        self.assertEqual(3, runner.call_count)
        import_command = runner.call_args_list[1].args[0]
        behavior_command = runner.call_args_list[2].args[0]
        self.assertIn("--import", import_command)
        self.assertNotIn("--editor", import_command)
        self.assertNotIn("--editor", behavior_command)

    def test_runtime_copy_starts_without_root_cache_and_preserves_nested_content(self) -> None:
        spec = load_fixture("sprint_course.json")
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            (project / ".godot").mkdir(parents=True)
            (project / ".godot" / "stale-cache").write_text("stale\n", encoding="utf-8")
            nested = project / "content" / ".godot"
            nested.mkdir(parents=True)
            (nested / "keep.txt").write_text("keep\n", encoding="utf-8")

            calls = 0

            def fake_run(command: list[str], timeout: int) -> tuple[int, str]:
                nonlocal calls
                del timeout
                calls += 1
                if calls == 1:
                    return 0, "4.7.2.stable.official\n"
                runtime_path = Path(command[command.index("--path") + 1])
                self.assertFalse((runtime_path / ".godot" / "stale-cache").exists())
                self.assertTrue((runtime_path / "content" / ".godot" / "keep.txt").is_file())
                if calls == 2:
                    (runtime_path / ".godot").mkdir()
                    (runtime_path / ".godot" / "fresh-import").write_text(
                        "fresh\n", encoding="utf-8"
                    )
                    return 0, "import ok\n"
                self.assertTrue((runtime_path / ".godot" / "fresh-import").is_file())
                return 0, mechanic_output(spec)

            with mock.patch.object(verify_project, "_run", side_effect=fake_run):
                errors, checks, evidence = verify_project._runtime_checks(
                    project, Path("/tmp/godot"), spec
                )
            self.assertEqual([], errors)
            self.assertIn("import", checks)
            self.assertIn("behavior", checks)
            self.assertEqual(0, evidence["exit_code"])

    def test_runtime_rejects_wrong_mechanic_count(self) -> None:
        spec = load_fixture("switch_vault.json")
        output = mechanic_output(spec).replace(
            "MECHANIC collectible PASS count=2",
            "MECHANIC collectible PASS count=1",
        )
        with mock.patch.object(
            verify_project,
            "_run",
            side_effect=[(0, "4.7.2.stable\n"), (0, "import ok\n"), (0, output)],
        ):
            errors, checks, evidence = verify_project._runtime_checks(
                Path("/tmp/example"), Path("/tmp/godot"), spec
            )
        self.assertIn("mechanic evidence mismatch for collectible", "\n".join(errors))
        self.assertNotIn("behavior", checks)
        self.assertEqual(1, evidence["mechanics"]["collectible"]["count"])

    def test_godot_error_allowlist_is_precise(self) -> None:
        allowed = (
            "ERROR: Failed to open 'user://logs/godot.log'.\n"
            "ERROR: Failed to open log file for writing: user://logs/godot.log\n"
            "ERROR: Cannot save file '/Users/test/Library/Application Support/Godot/editor_settings-4.7.tres'.\n"
            "ERROR: Error saving editor settings to /Users/test/Library/Application Support/Godot/editor_settings-4.7.tres\n"
            'ERROR: Condition "ret != noErr" is true. Returning: ""\n'
            "   at: get_system_ca_certificates (platform/macos/os_macos.mm:1035)\n"
        )
        self.assertEqual([], verify_project._godot_errors(allowed))
        rejected = allowed + "ERROR: Failed to load script res://main.gd\n"
        self.assertEqual(
            ["ERROR: Failed to load script res://main.gd"],
            verify_project._godot_errors(rejected),
        )
        self.assertEqual(
            [verify_project.MACOS_CA_ERROR],
            verify_project._godot_errors(verify_project.MACOS_CA_ERROR + "\n"),
        )

    def test_invalid_explicit_godot_does_not_silently_fallback(self) -> None:
        self.assertIsNone(verify_project._find_godot(Path("/definitely/missing/godot")))


if __name__ == "__main__":
    unittest.main()
