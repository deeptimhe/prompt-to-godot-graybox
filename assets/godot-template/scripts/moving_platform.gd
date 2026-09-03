class_name WhiteboxMovingPlatform
extends AnimatableBody3D

var object_id: StringName
var _start_position := Vector3.ZERO
var _end_position := Vector3.ZERO
var _one_way_duration := 2.0
var _elapsed := 0.0


func configure(
	new_id: StringName,
	platform_size: Vector3,
	platform_color: Color,
	origin: Vector3,
	travel_offset: Vector3,
	duration: float
) -> void:
	object_id = new_id
	name = str(object_id)
	set_meta("object_id", str(object_id))
	set_meta("object_type", "moving_platform")
	set_meta("size", platform_size)
	set_meta("color", platform_color)
	add_to_group("whitebox_object")
	add_to_group("moving_platform")
	sync_to_physics = true
	_start_position = origin
	_end_position = origin + travel_offset
	_one_way_duration = duration
	position = _start_position

	var mesh_instance := MeshInstance3D.new()
	var box_mesh := BoxMesh.new()
	box_mesh.size = platform_size
	mesh_instance.mesh = box_mesh
	mesh_instance.material_override = WhiteboxNodeSetup.material(platform_color)
	add_child(mesh_instance)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = platform_size
	collision.shape = shape
	add_child(collision)


func _physics_process(delta: float) -> void:
	advance_motion(delta)


func advance_motion(delta: float) -> void:
	_elapsed = fmod(_elapsed + delta, _one_way_duration * 2.0)
	var leg_progress := _elapsed / _one_way_duration
	var progress := leg_progress if leg_progress <= 1.0 else 2.0 - leg_progress
	position = _start_position.lerp(_end_position, progress)
