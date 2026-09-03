class_name WhiteboxNodeSetup
extends RefCounted


static func setup_area(
	area: Area3D,
	object_id: StringName,
	object_type: String,
	size: Vector3,
	color: Color,
	alpha: float
) -> void:
	area.name = str(object_id)
	area.set_meta("object_id", str(object_id))
	area.set_meta("object_type", object_type)
	area.set_meta("size", size)
	area.set_meta("color", color)
	area.add_to_group("whitebox_object")
	area.add_to_group(object_type)
	area.collision_layer = 0
	area.collision_mask = 2
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = "Visual"
	var box_mesh := BoxMesh.new()
	box_mesh.size = size
	mesh_instance.mesh = box_mesh
	var visible_color := color
	visible_color.a = alpha
	mesh_instance.material_override = material(visible_color, true)
	area.add_child(mesh_instance)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	area.add_child(collision)


static func material(color: Color, transparent := false) -> StandardMaterial3D:
	var result := StandardMaterial3D.new()
	result.albedo_color = color
	result.roughness = 1.0
	if transparent or color.a < 1.0:
		result.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		result.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return result
