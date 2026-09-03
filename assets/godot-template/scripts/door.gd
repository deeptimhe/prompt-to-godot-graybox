class_name WhiteboxDoor
extends StaticBody3D

var object_id: StringName
var requirements: Dictionary = {}
var _collision: CollisionShape3D
var _visual: MeshInstance3D
var _open := false


func configure(
	new_id: StringName,
	door_size: Vector3,
	door_color: Color,
	new_requirements: Dictionary
) -> void:
	object_id = new_id
	requirements = new_requirements.duplicate(true)
	name = str(object_id)
	set_meta("object_id", str(object_id))
	set_meta("object_type", "door")
	set_meta("size", door_size)
	set_meta("color", door_color)
	set_meta("requirements", requirements)
	add_to_group("whitebox_object")
	add_to_group("door")

	_visual = MeshInstance3D.new()
	_visual.name = "Visual"
	var box_mesh := BoxMesh.new()
	box_mesh.size = door_size
	_visual.mesh = box_mesh
	_visual.material_override = WhiteboxNodeSetup.material(door_color)
	add_child(_visual)

	_collision = CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = door_size
	_collision.shape = shape
	add_child(_collision)


func set_open(value: bool) -> void:
	_open = value
	_collision.set_deferred("disabled", _open)
	_visual.visible = not _open
	set_meta("is_open", _open)


func is_open() -> bool:
	return _open
