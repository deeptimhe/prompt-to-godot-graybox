class_name WhiteboxCollectible
extends Area3D

signal collected(actor: Node3D, collectible_id: StringName, value: int)

var object_id: StringName
var value := 1
var _collected := false


func configure(new_id: StringName, item_size: Vector3, item_color: Color, item_value: int) -> void:
	object_id = new_id
	value = item_value
	name = str(object_id)
	set_meta("object_id", str(object_id))
	set_meta("object_type", "collectible")
	set_meta("size", item_size)
	set_meta("color", item_color)
	set_meta("value", value)
	add_to_group("whitebox_object")
	add_to_group("collectible")
	collision_layer = 0
	collision_mask = 2

	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = "Visual"
	var sphere := SphereMesh.new()
	sphere.radius = minf(item_size.x, item_size.z) * 0.5
	sphere.height = item_size.y
	mesh_instance.mesh = sphere
	mesh_instance.material_override = WhiteboxNodeSetup.material(item_color)
	add_child(mesh_instance)

	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = item_size
	collision.shape = shape
	add_child(collision)
	body_entered.connect(_on_body_entered)


func reset_state() -> void:
	_collected = false
	monitoring = true
	visible = true


func _on_body_entered(body: Node3D) -> void:
	if _collected or not body is CharacterBody3D:
		return
	_collected = true
	set_deferred("monitoring", false)
	visible = false
	collected.emit(body, object_id, value)
