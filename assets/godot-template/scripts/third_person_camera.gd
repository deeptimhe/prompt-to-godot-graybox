class_name ThirdPersonCamera
extends Node3D

var target_offset := Vector3(0.0, 1.4, 0.0)
var follow_smoothing := 14.0
var mouse_sensitivity := 0.12
var stick_look_speed := 150.0
var initial_pitch_degrees := -10.0
var min_pitch_degrees := -55.0
var max_pitch_degrees := 70.0
var capture_mouse_on_start := true
var camera_distance := 6.5
var collision_margin := 0.15
var collision_mask := 1
var field_of_view := 70.0

var _follow_target: Node3D
var _pitch_pivot: Node3D
var _spring_arm: SpringArm3D
var _camera: Camera3D
var _yaw := 0.0
var _pitch := 0.0
var _excluded_target_rid: RID


func configure(data: Dictionary) -> void:
	camera_distance = float(data.get("distance", camera_distance))
	field_of_view = float(data.get("fov", field_of_view))
	initial_pitch_degrees = float(data.get("initial_pitch_degrees", initial_pitch_degrees))


func _ready() -> void:
	InputSetup.ensure_default_actions()
	top_level = true
	_resolve_or_create_camera_nodes()
	_yaw = rotation.y
	_pitch = deg_to_rad(initial_pitch_degrees)
	_apply_orbit_rotation()
	if capture_mouse_on_start and not DisplayServer.get_name().contains("headless"):
		capture_mouse()


func _physics_process(delta: float) -> void:
	var look_input := Input.get_vector(&"look_left", &"look_right", &"look_up", &"look_down")
	if look_input.length_squared() > 0.0:
		_yaw -= deg_to_rad(stick_look_speed) * look_input.x * delta
		_pitch -= deg_to_rad(stick_look_speed) * look_input.y * delta
		_clamp_pitch()
		_apply_orbit_rotation()

	if _follow_target == null:
		return
	var target_position := _follow_target.global_position + target_offset
	if follow_smoothing <= 0.0:
		global_position = target_position
	else:
		var weight := 1.0 - exp(-follow_smoothing * delta)
		global_position = global_position.lerp(target_position, weight)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"toggle_mouse_capture") and not event.is_echo():
		toggle_mouse_capture()
		get_viewport().set_input_as_handled()
		return
	var mouse_motion := event as InputEventMouseMotion
	if mouse_motion == null or Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	_yaw -= deg_to_rad(mouse_motion.relative.x * mouse_sensitivity)
	_pitch -= deg_to_rad(mouse_motion.relative.y * mouse_sensitivity)
	_clamp_pitch()
	_apply_orbit_rotation()
	get_viewport().set_input_as_handled()


func set_follow_target(target: Node3D) -> void:
	if _spring_arm != null and _excluded_target_rid.is_valid():
		_spring_arm.remove_excluded_object(_excluded_target_rid)
	_excluded_target_rid = RID()
	_follow_target = target
	if _follow_target == null:
		return
	snap_to_target()
	var collision_target := _follow_target as CollisionObject3D
	if collision_target != null and _spring_arm != null:
		_excluded_target_rid = collision_target.get_rid()
		_spring_arm.add_excluded_object(_excluded_target_rid)


func snap_to_target() -> void:
	if _follow_target != null:
		global_position = _follow_target.global_position + target_offset


func get_planar_forward() -> Vector3:
	var forward := -global_basis.z
	forward.y = 0.0
	return forward.normalized() if forward.length_squared() > 0.0001 else Vector3.FORWARD


func get_planar_right() -> Vector3:
	var right := global_basis.x
	right.y = 0.0
	return right.normalized() if right.length_squared() > 0.0001 else Vector3.RIGHT


func get_camera() -> Camera3D:
	return _camera


func capture_mouse() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func release_mouse() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func toggle_mouse_capture() -> void:
	if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		release_mouse()
	else:
		capture_mouse()


func _clamp_pitch() -> void:
	_pitch = clampf(_pitch, deg_to_rad(min_pitch_degrees), deg_to_rad(max_pitch_degrees))


func _apply_orbit_rotation() -> void:
	rotation.y = _yaw
	_pitch_pivot.rotation.x = _pitch


func _resolve_or_create_camera_nodes() -> void:
	_pitch_pivot = Node3D.new()
	_pitch_pivot.name = "PitchPivot"
	add_child(_pitch_pivot)
	_spring_arm = SpringArm3D.new()
	_spring_arm.name = "SpringArm3D"
	_pitch_pivot.add_child(_spring_arm)
	_spring_arm.spring_length = camera_distance
	_spring_arm.margin = collision_margin
	_spring_arm.collision_mask = collision_mask
	_camera = Camera3D.new()
	_camera.name = "Camera3D"
	_spring_arm.add_child(_camera)
	_camera.fov = field_of_view
	_camera.current = true
