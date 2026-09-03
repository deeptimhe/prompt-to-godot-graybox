class_name PlayerController
extends CharacterBody3D

signal jumped
signal landed(impact_speed: float)
signal respawned(spawn_position: Vector3)

var walk_speed := 5.5
var sprint_speed := 9.0
var acceleration := 28.0
var deceleration := 32.0
var air_control := 0.35
var turn_speed := 12.0
var gravity := 24.0
var jump_velocity := 8.5
var floor_snap_distance := 0.3
var floor_stick_speed := 0.5
var max_floor_angle_degrees := 50.0

var _camera_rig: ThirdPersonCamera
var _is_sprinting := false


func _ready() -> void:
	InputSetup.ensure_default_actions()
	motion_mode = CharacterBody3D.MOTION_MODE_GROUNDED
	up_direction = Vector3.UP
	floor_stop_on_slope = true
	floor_block_on_wall = true
	floor_constant_speed = true
	floor_snap_length = floor_snap_distance
	floor_max_angle = deg_to_rad(max_floor_angle_degrees)


func configure(data: Dictionary) -> void:
	walk_speed = float(data.get("walk_speed", walk_speed))
	sprint_speed = float(data.get("sprint_speed", sprint_speed))
	acceleration = float(data.get("acceleration", acceleration))
	deceleration = float(data.get("deceleration", deceleration))
	air_control = float(data.get("air_control", air_control))
	turn_speed = float(data.get("turn_speed", turn_speed))
	gravity = float(data.get("gravity", gravity))
	jump_velocity = float(data.get("jump_velocity", jump_velocity))


func _physics_process(delta: float) -> void:
	var was_on_floor := is_on_floor()
	var move_input := Input.get_vector(
		&"move_left", &"move_right", &"move_forward", &"move_back"
	)
	var move_direction := _camera_relative_direction(move_input)
	_is_sprinting = move_input.length_squared() > 0.0 and Input.is_action_pressed(&"sprint")
	var target_speed := sprint_speed if _is_sprinting else walk_speed
	var desired_horizontal := move_direction * target_speed * minf(move_input.length(), 1.0)
	var horizontal_velocity := Vector3(velocity.x, 0.0, velocity.z)
	var rate := acceleration if desired_horizontal.length_squared() > 0.0 else deceleration
	if not was_on_floor:
		rate *= air_control
	horizontal_velocity = horizontal_velocity.move_toward(desired_horizontal, rate * delta)
	velocity.x = horizontal_velocity.x
	velocity.z = horizontal_velocity.z

	if was_on_floor:
		if Input.is_action_just_pressed(&"jump"):
			try_jump()
		elif velocity.y <= 0.0:
			velocity.y = -floor_stick_speed
	else:
		velocity.y -= gravity * delta

	if move_direction.length_squared() > 0.0001:
		var target_yaw := atan2(-move_direction.x, -move_direction.z)
		rotation.y = rotate_toward(rotation.y, target_yaw, turn_speed * delta)

	var impact_speed := maxf(-velocity.y, 0.0)
	move_and_slide()
	if not was_on_floor and is_on_floor():
		landed.emit(impact_speed)


func set_camera_rig(rig: ThirdPersonCamera) -> void:
	_camera_rig = rig
	if _camera_rig != null:
		_camera_rig.set_follow_target(self)


func respawn(spawn_position: Vector3) -> void:
	global_position = spawn_position
	velocity = Vector3.ZERO
	_is_sprinting = false
	if _camera_rig != null:
		_camera_rig.snap_to_target()
	respawned.emit(spawn_position)


func is_sprinting() -> bool:
	return _is_sprinting


func get_horizontal_speed() -> float:
	return Vector2(velocity.x, velocity.z).length()


func try_jump() -> bool:
	if not is_on_floor():
		return false
	velocity.y = jump_velocity
	jumped.emit()
	return true


func _camera_relative_direction(move_input: Vector2) -> Vector3:
	var forward := Vector3.FORWARD
	var right := Vector3.RIGHT
	if _camera_rig != null:
		forward = _camera_rig.get_planar_forward()
		right = _camera_rig.get_planar_right()
	var direction := right * move_input.x + forward * -move_input.y
	return direction.normalized() if direction.length_squared() > 0.0001 else Vector3.ZERO
