class_name WhiteboxSwitch
extends Area3D

signal activated(actor: Node3D, switch_id: StringName)

var object_id: StringName
var _active := false
var _visual: MeshInstance3D
var _inactive_color := Color.WHITE


func configure(new_id: StringName, zone_size: Vector3, zone_color: Color) -> void:
	object_id = new_id
	_inactive_color = zone_color
	name = str(object_id)
	set_meta("object_id", str(object_id))
	set_meta("object_type", "switch")
	set_meta("size", zone_size)
	set_meta("color", zone_color)
	add_to_group("whitebox_object")
	add_to_group("switch")
	collision_layer = 0
	collision_mask = 2

	_visual = MeshInstance3D.new()
	_visual.name = "Visual"
	var box_mesh := BoxMesh.new()
	box_mesh.size = zone_size
	_visual.mesh = box_mesh
	_visual.material_override = WhiteboxNodeSetup.material(zone_color)
	add_child(_visual)

	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = zone_size
	collision.shape = shape
	add_child(collision)
	body_entered.connect(_on_body_entered)


func reset_state() -> void:
	_active = false
	_visual.material_override = WhiteboxNodeSetup.material(_inactive_color)


func is_active() -> bool:
	return _active


func _on_body_entered(body: Node3D) -> void:
	if _active or not body is CharacterBody3D:
		return
	_active = true
	_visual.material_override = WhiteboxNodeSetup.material(_inactive_color.lightened(0.42))
	activated.emit(body, object_id)
