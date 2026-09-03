extends Node3D

signal run_completed(goal_id: StringName)

const PlayerScript = preload("res://scripts/player_controller.gd")
const CameraScript = preload("res://scripts/third_person_camera.gd")
const WorldBuilderScript = preload("res://scripts/world_builder.gd")
const HUDScript = preload("res://scripts/hud.gd")

var player: PlayerController
var camera_rig: ThirdPersonCamera
var world: WhiteboxWorldBuilder
var hud: GrayboxHUD
var game_spec: Dictionary = {}
var collected_value := 0
var collected_ids: Dictionary = {}
var active_switches: Dictionary = {}
var elapsed := 0.0
var completed := false
var spec_path := "res://data/game_spec.json"
var _goal_inputs_enabled := true
var _goal_clear_physics_frames := 0


func _ready() -> void:
	game_spec = _load_spec(spec_path)
	if game_spec.is_empty():
		push_error("Cannot start without a valid JSON object at %s" % spec_path)
		return
	_create_lighting()
	_create_camera()
	_create_player()
	_create_world()
	_create_hud()
	_update_progress()


func _process(delta: float) -> void:
	if not completed:
		elapsed += delta
		if hud != null:
			hud.set_elapsed(elapsed)
	if player != null and player.global_position.y < -12.0:
		_respawn_player()


func _physics_process(_delta: float) -> void:
	if _goal_inputs_enabled or player == null:
		return
	if _player_overlaps_goal():
		_goal_clear_physics_frames = 0
		return
	_goal_clear_physics_frames += 1
	if _goal_clear_physics_frames >= 2:
		_goal_inputs_enabled = true
		if hud != null and not completed:
			hud.set_status("Exploring")


func _unhandled_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo:
		if key.physical_keycode == KEY_R:
			_respawn_player()
			get_viewport().set_input_as_handled()
		elif completed and key.physical_keycode == KEY_ENTER:
			_restart_run()
			get_viewport().set_input_as_handled()
	var button := event as InputEventJoypadButton
	if button != null and button.pressed:
		if button.button_index == JOY_BUTTON_BACK:
			_respawn_player()
			get_viewport().set_input_as_handled()
		elif completed and button.button_index == JOY_BUTTON_START:
			_restart_run()
			get_viewport().set_input_as_handled()


func _create_lighting() -> void:
	var world_environment := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("#20242B")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("#DCE4EF")
	environment.ambient_light_energy = 0.38
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	world_environment.environment = environment
	add_child(world_environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52.0, -28.0, 0.0)
	sun.light_energy = 0.62
	sun.shadow_enabled = true
	add_child(sun)


func _create_camera() -> void:
	camera_rig = CameraScript.new()
	camera_rig.name = "ThirdPersonCamera"
	camera_rig.configure(game_spec.get("camera", {}))
	add_child(camera_rig)


func _create_player() -> void:
	player = PlayerScript.new()
	player.name = "Player"
	player.collision_layer = 2
	player.collision_mask = 1
	player.add_to_group("player")
	player.configure(game_spec.get("player", {}))
	var collision := CollisionShape3D.new()
	var shape := CapsuleShape3D.new()
	shape.radius = 0.4
	shape.height = 1.8
	collision.shape = shape
	player.add_child(collision)
	var mesh_instance := MeshInstance3D.new()
	var capsule := CapsuleMesh.new()
	capsule.radius = 0.4
	capsule.height = 1.8
	mesh_instance.mesh = capsule
	mesh_instance.material_override = WhiteboxNodeSetup.material(Color("#5E9EFF"))
	player.add_child(mesh_instance)
	var facing := MeshInstance3D.new()
	facing.position = Vector3(0.0, 0.2, -0.48)
	var marker_mesh := BoxMesh.new()
	marker_mesh.size = Vector3(0.18, 0.18, 0.45)
	facing.mesh = marker_mesh
	facing.material_override = WhiteboxNodeSetup.material(Color("#EAF2FF"))
	player.add_child(facing)
	add_child(player)
	player.set_camera_rig(camera_rig)


func _create_world() -> void:
	world = WorldBuilderScript.new()
	world.name = "World"
	world.level_built.connect(_on_level_built)
	world.hazard_entered.connect(_on_hazard_entered)
	world.collectible_entered.connect(_on_collectible_entered)
	world.switch_entered.connect(_on_switch_entered)
	world.goal_entered.connect(_on_goal_entered)
	add_child(world)
	if not world.build_spec(game_spec):
		push_error("Unable to build the graybox world")
	world.update_doors(collected_value, active_switches)


func _create_hud() -> void:
	hud = HUDScript.new()
	hud.name = "HUD"
	hud.configure(game_spec.get("game", {}), world.total_collectible_value)
	add_child(hud)


func _on_level_built(_spawn_position: Vector3) -> void:
	var spawn_transform := world.get_spawn_transform()
	player.rotation = spawn_transform.basis.get_euler()
	player.respawn(spawn_transform.origin)


func _on_hazard_entered(actor: Node3D, _hazard_id: StringName) -> void:
	if actor == player and not completed:
		_respawn_player()


func _on_collectible_entered(
	actor: Node3D, collectible_id: StringName, value: int
) -> void:
	if actor != player or completed or collected_ids.has(str(collectible_id)):
		return
	collected_ids[str(collectible_id)] = true
	collected_value += value
	_update_progress()


func _on_switch_entered(actor: Node3D, switch_id: StringName) -> void:
	if actor != player or completed or active_switches.has(str(switch_id)):
		return
	active_switches[str(switch_id)] = true
	_update_progress()


func _on_goal_entered(actor: Node3D, goal_id: StringName) -> void:
	if actor != player or completed or not _goal_inputs_enabled:
		return
	var requirements := world.get_requirements(goal_id)
	if not world.requirements_met(requirements, collected_value, active_switches):
		hud.show_locked_requirements(requirements, collected_value, active_switches)
		return
	completed = true
	player.velocity = Vector3.ZERO
	hud.show_completion(elapsed)
	run_completed.emit(goal_id)


func _update_progress() -> void:
	if world != null:
		world.update_doors(collected_value, active_switches)
	if hud != null:
		hud.set_progress(collected_value, active_switches.size())
		hud.set_status("Exploring")


func _respawn_player() -> void:
	if world == null or player == null:
		return
	var spawn_transform := world.get_spawn_transform()
	player.rotation = spawn_transform.basis.get_euler()
	player.respawn(spawn_transform.origin)
	if hud != null and not completed:
		hud.set_status("Returned to spawn")


func _restart_run() -> void:
	_goal_inputs_enabled = false
	_goal_clear_physics_frames = 0
	completed = false
	elapsed = 0.0
	collected_value = 0
	collected_ids.clear()
	active_switches.clear()
	var restart_spawn := world.get_spawn_transform()
	player.rotation = restart_spawn.basis.get_euler()
	player.respawn(restart_spawn.origin)
	if not world.build_spec(game_spec):
		push_error("Unable to rebuild the graybox world")
	world.update_doors(collected_value, active_switches)
	hud.hide_completion()
	hud.set_status("Exploring")
	hud.set_progress(0, 0)
	hud.set_elapsed(0.0)


func _player_overlaps_goal() -> bool:
	for node: Node in get_tree().get_nodes_in_group("goal"):
		var goal := node as Area3D
		if goal != null and goal.overlaps_body(player):
			return true
	return false


func _load_spec(path: String) -> Dictionary:
	var source := FileAccess.get_file_as_string(path)
	if source.is_empty():
		return {}
	var parsed: Variant = JSON.parse_string(source)
	return parsed if typeof(parsed) == TYPE_DICTIONARY else {}
