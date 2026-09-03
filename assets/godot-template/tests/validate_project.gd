extends SceneTree

const PASS_MARKER := "PASS: prompt-to-godot-graybox runtime validation"
const MECHANIC_NAMES: PackedStringArray = [
	"controller", "camera", "hazard", "moving_platform", "collectible",
	"switch", "door", "goal", "restart",
]

var failures: Array[String] = []
var mechanic_failures: Dictionary = {}
var mechanic_counts: Dictionary = {
	"controller": 1,
	"camera": 1,
	"hazard": 0,
	"moving_platform": 0,
	"collectible": 0,
	"switch": 0,
	"door": 0,
	"goal": 0,
	"restart": 1,
}
var completion_events := 0


func _initialize() -> void:
	for mechanic: String in MECHANIC_NAMES:
		mechanic_failures[mechanic] = []
	_run.call_deferred()


func _run() -> void:
	var fixture_path := "res://data/game_spec.json"
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--fixture="):
			fixture_path = argument.trim_prefix("--fixture=")
	var packed := load("res://main.tscn") as PackedScene
	_check(packed != null, "main.tscn loads")
	if packed == null:
		_finish()
		return
	var main := packed.instantiate()
	main.spec_path = fixture_path
	root.add_child(main)
	await process_frame
	await physics_frame
	var world := main.world as WhiteboxWorldBuilder
	var player := main.player as PlayerController
	var camera := main.camera_rig as ThirdPersonCamera
	_check(world != null, "world is created")
	_check(player != null, "player is created")
	_check(camera != null and camera.get_camera() != null, "third-person camera is created")
	if world == null or player == null or camera == null:
		_finish()
		return
	main.run_completed.connect(_on_run_completed)
	var spec: Dictionary = main.game_spec
	var objects: Array = spec["objects"]
	_check(world.objects_by_id.size() == objects.size(), "all spec objects are built")

	var expected_collectible_value := 0
	var collectible_specs: Array[Dictionary] = []
	var switch_specs: Array[Dictionary] = []
	var door_specs: Array[Dictionary] = []
	var goal_specs: Array[Dictionary] = []
	var hazard_specs: Array[Dictionary] = []
	var moving_specs: Array[Dictionary] = []
	for object_value: Variant in objects:
		var object_spec: Dictionary = object_value
		var object_id := StringName(object_spec["id"])
		var object_type := str(object_spec["type"])
		var built := world.get_object(object_id)
		_check(built != null, "object '%s' is queryable" % object_id)
		_check(built != null and built.is_in_group(object_type), "object '%s' has its type group" % object_id)
		match object_type:
			"collectible":
				collectible_specs.append(object_spec)
				expected_collectible_value += int(object_spec.get("value", 1))
			"switch": switch_specs.append(object_spec)
			"door": door_specs.append(object_spec)
			"goal": goal_specs.append(object_spec)
			"hazard": hazard_specs.append(object_spec)
			"moving_platform": moving_specs.append(object_spec)
	mechanic_counts["hazard"] = hazard_specs.size()
	mechanic_counts["moving_platform"] = moving_specs.size()
	mechanic_counts["collectible"] = collectible_specs.size()
	mechanic_counts["switch"] = switch_specs.size()
	mechanic_counts["door"] = door_specs.size()
	mechanic_counts["goal"] = goal_specs.size()
	_check(world.total_collectible_value == expected_collectible_value, "collectible total comes from the spec")

	var player_config: Dictionary = spec["player"]
	for key: String in player_config:
		_check(is_equal_approx(float(player.get(key)), float(player_config[key])), "player.%s is applied" % key)
	var camera_config: Dictionary = spec["camera"]
	_check(is_equal_approx(camera.camera_distance, float(camera_config["distance"])), "camera distance is applied")
	_check(is_equal_approx(camera.get_camera().fov, float(camera_config["fov"])), "camera FOV is applied")
	_check(is_equal_approx(camera.initial_pitch_degrees, float(camera_config["initial_pitch_degrees"])), "camera pitch is applied")
	await _test_controller(player)
	_test_camera(player, camera, camera_config)

	for moving_spec: Dictionary in moving_specs:
		var built_platform := world.get_object(StringName(moving_spec["id"])) as WhiteboxMovingPlatform
		var built_collision := _find_collision(built_platform)
		_mechanic_check(
			"moving_platform",
			built_platform != null and built_collision != null and not built_collision.disabled,
			"moving platform '%s' has active collision" % moving_spec["id"]
		)
		var probe := WhiteboxMovingPlatform.new()
		var start := _vector3(moving_spec["transform"]["position"])
		var offset := _vector3(moving_spec["movement"]["offset"])
		var finish := start + offset
		var duration := float(moving_spec["movement"]["duration"])
		probe.configure(&"motion_probe", _vector3(moving_spec["size"]), Color.WHITE, start, offset, duration)
		probe.advance_motion(duration)
		_mechanic_check(
			"moving_platform", probe.position.is_equal_approx(finish),
			"moving platform '%s' reaches endpoint" % moving_spec["id"]
		)
		probe.advance_motion(duration)
		_mechanic_check(
			"moving_platform", probe.position.is_equal_approx(start),
			"moving platform '%s' reverses to start" % moving_spec["id"]
		)
		var probe_collision := _find_collision(probe)
		_mechanic_check(
			"moving_platform",
			probe_collision != null and probe_collision.shape != null and not probe_collision.disabled,
			"moving platform '%s' motion probe retains collision" % moving_spec["id"]
		)
		probe.free()

	for door_spec: Dictionary in door_specs:
		var door := world.get_object(StringName(door_spec["id"])) as WhiteboxDoor
		var requirements: Dictionary = door_spec.get("requirements", {})
		var initially_open := _requirements_satisfied(requirements, 0, {})
		var door_collision := _find_collision(door)
		_mechanic_check(
			"door", door != null and door.is_open() == initially_open,
			"door '%s' initial state follows requirements" % door_spec["id"]
		)
		_mechanic_check(
			"door",
			door_collision != null and door_collision.disabled == initially_open,
			"door '%s' initial collision matches open state" % door_spec["id"]
		)
	for collectible_spec: Dictionary in collectible_specs:
		var collectible := world.get_object(StringName(collectible_spec["id"])) as WhiteboxCollectible
		var value_before: int = main.collected_value
		collectible.call("_on_body_entered", player)
		collectible.call("_on_body_entered", player)
		await process_frame
		_mechanic_check(
			"collectible",
			main.collected_value == value_before + int(collectible_spec.get("value", 1)),
			"collectible '%s' counts exactly once" % collectible_spec["id"]
		)
		_mechanic_check(
			"collectible", not collectible.visible and not collectible.monitoring,
			"collectible '%s' hides and disables" % collectible_spec["id"]
		)
	for switch_spec: Dictionary in switch_specs:
		var switch_zone := world.get_object(StringName(switch_spec["id"])) as WhiteboxSwitch
		switch_zone.call("_on_body_entered", player)
		switch_zone.call("_on_body_entered", player)
		_mechanic_check(
			"switch", switch_zone.is_active(),
			"switch '%s' stays active" % switch_spec["id"]
		)
		_mechanic_check(
			"switch", main.active_switches.has(str(switch_spec["id"])),
			"switch '%s' records progress exactly once" % switch_spec["id"]
		)
	if not collectible_specs.is_empty():
		_mechanic_check(
			"collectible", main.collected_value == expected_collectible_value,
			"all collectible values accumulate"
		)
	if not switch_specs.is_empty():
		_mechanic_check(
			"switch", main.active_switches.size() == switch_specs.size(),
			"all switches activate once"
		)
	var collectible_progress: int = main.collected_value
	var collected_id_progress: Dictionary = main.collected_ids.duplicate()
	var switch_progress: Dictionary = main.active_switches.duplicate()
	for hazard_spec: Dictionary in hazard_specs:
		var hazard := world.get_object(StringName(hazard_spec["id"])) as WhiteboxHazardZone
		_mechanic_check(
			"hazard", hazard != null,
			"hazard '%s' is a WhiteboxHazardZone" % hazard_spec["id"]
		)
		player.global_position = Vector3(900.0, 900.0, 900.0)
		player.velocity = Vector3(5.0, -9.0, 3.0)
		if hazard != null:
			hazard.call("_on_body_entered", player)
		_mechanic_check(
			"hazard", player.global_position.is_equal_approx(world.get_spawn_transform().origin),
			"hazard '%s' respawns at the exact spawn" % hazard_spec["id"]
		)
		_mechanic_check(
			"hazard", player.velocity.is_zero_approx(),
			"hazard '%s' clears player velocity" % hazard_spec["id"]
		)
		_mechanic_check(
			"hazard",
			main.collected_value == collectible_progress
				and main.collected_ids == collected_id_progress
				and main.active_switches == switch_progress,
			"hazard '%s' preserves all run progress" % hazard_spec["id"]
		)
	await physics_frame
	await physics_frame

	for door_spec: Dictionary in door_specs:
		await _test_door_requirements(world, door_spec)
	world.update_doors(main.collected_value, main.active_switches)
	await physics_frame
	await physics_frame

	_check(not goal_specs.is_empty(), "spec contains a goal")
	for goal_spec: Dictionary in goal_specs:
		_test_goal_requirements(main, world, player, goal_spec)
	main.collected_value = collectible_progress
	main.collected_ids = collected_id_progress.duplicate()
	main.active_switches = switch_progress.duplicate()

	if not goal_specs.is_empty():
		player.global_position = _vector3(goal_specs[0]["transform"]["position"])
		await physics_frame
		await physics_frame
	main.call("_restart_run")
	var restart_elapsed_ok: bool = float(main.elapsed) < 0.01
	var restart_player_position_ok := player.global_position.is_equal_approx(
		world.get_spawn_transform().origin
	)
	var restart_player_velocity_ok := player.velocity.is_zero_approx()
	var restart_moving_positions: Dictionary = {}
	for moving_spec: Dictionary in moving_specs:
		var moving := world.get_object(StringName(moving_spec["id"])) as WhiteboxMovingPlatform
		restart_moving_positions[str(moving_spec["id"])] = (
			moving != null
			and moving.position.is_equal_approx(_vector3(moving_spec["transform"]["position"]))
		)
	for unused: int in 120:
		await physics_frame
		await process_frame
		if bool(main.get("_goal_inputs_enabled")):
			break
	_mechanic_check(
		"restart", not main.completed and main.collected_value == 0 and main.collected_ids.is_empty(),
		"restart resets completion and collectibles"
	)
	_mechanic_check(
		"restart", main.active_switches.is_empty() and restart_elapsed_ok,
		"restart resets switches and timer"
	)
	_mechanic_check(
		"restart", bool(main.get("_goal_inputs_enabled")),
		"restart re-enables goal input after the player clears every goal zone"
	)
	var restart_status := main.hud.get("_status_label") as Label
	_mechanic_check(
		"restart", restart_status != null and restart_status.text == "Exploring",
		"restart restores the HUD status without a stale goal-lock message"
	)
	_mechanic_check(
		"restart", restart_player_position_ok,
		"restart returns player to spawn"
	)
	_mechanic_check("restart", restart_player_velocity_ok, "restart clears player velocity")
	_mechanic_check(
		"restart", world.objects_by_id.size() == objects.size(),
		"restart rebuilds the exact spec object count"
	)
	for object_value: Variant in objects:
		var object_spec: Dictionary = object_value
		var rebuilt := world.get_object(StringName(object_spec["id"]))
		_mechanic_check(
			"restart",
			rebuilt != null and rebuilt.is_in_group(str(object_spec["type"])),
			"restart restores object '%s'" % object_spec["id"]
		)
	for collectible_spec: Dictionary in collectible_specs:
		var collectible := world.get_object(StringName(collectible_spec["id"])) as WhiteboxCollectible
		_mechanic_check(
			"restart", collectible.visible and collectible.monitoring,
			"restart restores collectible '%s'" % collectible_spec["id"]
		)
	for switch_spec: Dictionary in switch_specs:
		var switch_zone := world.get_object(StringName(switch_spec["id"])) as WhiteboxSwitch
		_mechanic_check(
			"restart", not switch_zone.is_active(),
			"restart clears switch '%s'" % switch_spec["id"]
		)
	for door_spec: Dictionary in door_specs:
		var door := world.get_object(StringName(door_spec["id"])) as WhiteboxDoor
		var should_be_open := _requirements_satisfied(door.requirements, 0, {})
		var collision := _find_collision(door)
		_mechanic_check(
			"restart",
			door.is_open() == should_be_open and collision != null and collision.disabled == should_be_open,
			"restart restores door '%s' state and collision" % door_spec["id"]
		)
	for moving_spec: Dictionary in moving_specs:
		_mechanic_check(
			"restart",
			bool(restart_moving_positions.get(str(moving_spec["id"]), false)),
			"restart returns moving platform '%s' to its start" % moving_spec["id"]
		)
	for hazard_spec: Dictionary in hazard_specs:
		var hazard := world.get_object(StringName(hazard_spec["id"])) as Area3D
		_mechanic_check(
			"restart", hazard != null and hazard.monitoring,
			"restart re-enables hazard '%s'" % hazard_spec["id"]
		)
	for goal_spec: Dictionary in goal_specs:
		var goal := world.get_object(StringName(goal_spec["id"])) as Area3D
		_mechanic_check(
			"restart", goal != null and goal.monitoring,
			"restart re-enables goal '%s'" % goal_spec["id"]
		)
	_finish()


func _test_controller(player: PlayerController) -> void:
	var floor := StaticBody3D.new()
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(20, 0.5, 20)
	collision.shape = shape
	floor.add_child(collision)
	floor.position = Vector3(1000.0, 8.85, 1000.0)
	root.add_child(floor)
	player.respawn(Vector3(1000.0, 10.0, 1000.0))
	var grounded := false
	for unused in 60:
		await physics_frame
		if player.is_on_floor():
			grounded = true
			break
	_mechanic_check("controller", grounded, "controller settles onto a floor")
	var movement_start := player.global_position
	Input.action_press(&"move_forward")
	for unused in 12:
		await physics_frame
	Input.action_release(&"move_forward")
	var horizontal_displacement := Vector2(
		player.global_position.x - movement_start.x,
		player.global_position.z - movement_start.z
	).length()
	_mechanic_check(
		"controller", horizontal_displacement > 0.05,
		"controller input produces actual horizontal displacement"
	)
	for unused in 30:
		await physics_frame
		if player.is_on_floor():
			break
	var jump_start_y := player.global_position.y
	var jumped := player.try_jump()
	_mechanic_check(
		"controller", jumped and player.velocity.y > 0.0,
		"controller performs a grounded jump"
	)
	var left_floor := false
	var landed_again := false
	var peak_y := jump_start_y
	for unused in 240:
		await physics_frame
		peak_y = maxf(peak_y, player.global_position.y)
		if not player.is_on_floor():
			left_floor = true
		elif left_floor:
			landed_again = true
			break
	_mechanic_check(
		"controller", left_floor and peak_y > jump_start_y + 0.25,
		"controller jump produces upward displacement"
	)
	_mechanic_check("controller", landed_again, "controller lands after jumping")
	floor.queue_free()
	player.respawn(Vector3.ZERO)


func _test_camera(
	player: PlayerController, camera: ThirdPersonCamera, camera_config: Dictionary
) -> void:
	player.global_position += Vector3(3, 0, -2)
	camera.snap_to_target()
	_mechanic_check(
		"camera", camera.global_position.is_equal_approx(player.global_position + camera.target_offset),
		"camera follows the player"
	)
	var spring_arm := camera.get_node_or_null("PitchPivot/SpringArm3D") as SpringArm3D
	var pitch_pivot := camera.get_node_or_null("PitchPivot") as Node3D
	_mechanic_check("camera", spring_arm != null, "camera owns a SpringArm3D")
	_mechanic_check(
		"camera",
		spring_arm != null and spring_arm.collision_mask == camera.collision_mask
			and spring_arm.collision_mask != 0,
		"camera SpringArm3D has the configured nonzero collision mask"
	)
	_mechanic_check(
		"camera",
		spring_arm != null
			and is_equal_approx(spring_arm.spring_length, float(camera_config["distance"])),
		"camera SpringArm3D applies spec.camera.distance"
	)
	_mechanic_check(
		"camera",
		pitch_pivot != null
			and is_equal_approx(
				pitch_pivot.rotation.x,
				deg_to_rad(float(camera_config["initial_pitch_degrees"]))
			),
		"camera PitchPivot applies spec.camera.initial_pitch_degrees"
	)


func _test_door_requirements(world: WhiteboxWorldBuilder, door_spec: Dictionary) -> void:
	var door := world.get_object(StringName(door_spec["id"])) as WhiteboxDoor
	var requirements: Dictionary = door_spec.get("requirements", {})
	var required_collectibles := int(requirements.get("collectibles", 0))
	var required_switches: Array = requirements.get("switches", [])
	var all_required_switches := _switch_dictionary(required_switches)
	if required_collectibles > 0:
		await _assert_door_state(
			world, door, required_collectibles - 1, all_required_switches, false,
			"door '%s' stays closed with one collectible point missing" % door_spec["id"]
		)
	for required_switch: Variant in required_switches:
		var missing_switches := all_required_switches.duplicate()
		missing_switches.erase(str(required_switch))
		await _assert_door_state(
			world, door, required_collectibles, missing_switches, false,
			"door '%s' stays closed without switch '%s'" % [door_spec["id"], required_switch]
		)
	await _assert_door_state(
		world, door, required_collectibles, all_required_switches, true,
		"door '%s' opens when requirements are exactly met" % door_spec["id"]
	)


func _assert_door_state(
	world: WhiteboxWorldBuilder,
	door: WhiteboxDoor,
	collectibles: int,
	switches: Dictionary,
	expected_open: bool,
	message: String
) -> void:
	world.update_doors(collectibles, switches)
	await physics_frame
	await physics_frame
	var collision := _find_collision(door)
	_mechanic_check(
		"door", door != null and door.is_open() == expected_open,
		message
	)
	_mechanic_check(
		"door", collision != null and collision.disabled == expected_open,
		"%s; collision must match" % message
	)


func _test_goal_requirements(
	main: Node, world: WhiteboxWorldBuilder, player: PlayerController, goal_spec: Dictionary
) -> void:
	var goal := world.get_object(StringName(goal_spec["id"])) as WhiteboxGoalZone
	_mechanic_check(
		"goal", goal != null,
		"goal '%s' is a WhiteboxGoalZone" % goal_spec["id"]
	)
	if goal == null:
		return
	var requirements: Dictionary = goal_spec.get("requirements", {})
	var required_collectibles := int(requirements.get("collectibles", 0))
	var required_switches: Array = requirements.get("switches", [])
	var all_required_switches := _switch_dictionary(required_switches)
	if required_collectibles > 0:
		_assert_goal_locked(
			main, goal, player, required_collectibles - 1, all_required_switches,
			"goal '%s' stays locked with one collectible point missing" % goal_spec["id"]
		)
	for required_switch: Variant in required_switches:
		var missing_switches := all_required_switches.duplicate()
		missing_switches.erase(str(required_switch))
		_assert_goal_locked(
			main, goal, player, required_collectibles, missing_switches,
			"goal '%s' stays locked without switch '%s'" % [goal_spec["id"], required_switch]
		)
	main.completed = false
	main.collected_value = required_collectibles
	main.active_switches = all_required_switches.duplicate()
	player.velocity = Vector3(4.0, 2.0, -3.0)
	var events_before: int = completion_events
	goal.call("_on_body_entered", player)
	_mechanic_check(
		"goal", main.completed,
		"goal '%s' completes when requirements are exactly met" % goal_spec["id"]
	)
	_mechanic_check(
		"goal", completion_events == events_before + 1,
		"goal '%s' emits run_completed exactly once" % goal_spec["id"]
	)
	_mechanic_check(
		"goal", player.velocity.is_zero_approx(),
		"goal '%s' stops the player" % goal_spec["id"]
	)
	goal.call("_on_body_entered", player)
	_mechanic_check(
		"goal", main.completed and completion_events == events_before + 1,
		"goal '%s' completion is idempotent" % goal_spec["id"]
	)


func _assert_goal_locked(
	main: Node,
	goal: WhiteboxGoalZone,
	player: PlayerController,
	collectibles: int,
	switches: Dictionary,
	message: String
) -> void:
	main.completed = false
	main.collected_value = collectibles
	main.active_switches = switches.duplicate()
	var events_before: int = completion_events
	goal.call("_on_body_entered", player)
	_mechanic_check("goal", not main.completed, message)
	_mechanic_check(
		"goal", completion_events == events_before,
		"%s; run_completed must not emit" % message
	)


func _switch_dictionary(switch_ids: Array) -> Dictionary:
	var result: Dictionary = {}
	for switch_id: Variant in switch_ids:
		result[str(switch_id)] = true
	return result


func _requirements_satisfied(
	requirements: Dictionary, collectibles: int, switches: Dictionary
) -> bool:
	if collectibles < int(requirements.get("collectibles", 0)):
		return false
	for switch_id: Variant in requirements.get("switches", []):
		if not switches.has(str(switch_id)):
			return false
	return true


func _check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)


func _mechanic_check(mechanic: String, condition: bool, message: String) -> void:
	if condition:
		return
	failures.append("%s: %s" % [mechanic, message])
	var entries: Array = mechanic_failures[mechanic]
	entries.append(message)


func _on_run_completed(_goal_id: StringName) -> void:
	completion_events += 1


func _find_collision(node: Node) -> CollisionShape3D:
	if node == null:
		return null
	for child: Node in node.get_children():
		var collision := child as CollisionShape3D
		if collision != null:
			return collision
	return null


func _vector3(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func _finish() -> void:
	for mechanic: String in MECHANIC_NAMES:
		var count := int(mechanic_counts[mechanic])
		var status := "N/A"
		if count > 0 and (mechanic_failures[mechanic] as Array).is_empty():
			status = "PASS"
		print("MECHANIC %s %s count=%d" % [mechanic, status, count])
	if failures.is_empty():
		print(PASS_MARKER)
		quit(0)
		return
	for failure: String in failures:
		push_error("VALIDATION: %s" % failure)
	quit(1)
