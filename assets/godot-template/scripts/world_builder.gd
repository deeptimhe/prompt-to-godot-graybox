class_name WhiteboxWorldBuilder
extends Node3D

signal level_built(spawn_position: Vector3)
signal level_loaded(spec: Dictionary)
signal build_failed(errors: PackedStringArray)
signal hazard_entered(actor: Node3D, hazard_id: StringName)
signal collectible_entered(actor: Node3D, collectible_id: StringName, value: int)
signal switch_entered(actor: Node3D, switch_id: StringName)
signal goal_entered(actor: Node3D, goal_id: StringName)

const SUPPORTED_VERSION := 1
const SUPPORTED_TYPES := [
	"static_box", "ramp", "moving_platform", "hazard", "collectible",
	"switch", "door", "goal", "marker",
]
const MovingPlatformScript = preload("res://scripts/moving_platform.gd")
const HazardZoneScript = preload("res://scripts/hazard_zone.gd")
const CollectibleScript = preload("res://scripts/collectible.gd")
const SwitchScript = preload("res://scripts/switch_zone.gd")
const DoorScript = preload("res://scripts/door.gd")
const GoalZoneScript = preload("res://scripts/goal_zone.gd")

var spawn_position := Vector3.ZERO
var spawn_rotation_degrees := Vector3.ZERO
var objects_by_id: Dictionary = {}
var level_data: Dictionary = {}
var total_collectible_value := 0


func build_level(path: String = "res://data/game_spec.json") -> bool:
	var source := FileAccess.get_file_as_string(path)
	if source.is_empty():
		_fail(PackedStringArray(["Could not read game spec: %s" % path]))
		return false
	var parsed: Variant = JSON.parse_string(source)
	if typeof(parsed) != TYPE_DICTIONARY:
		_fail(PackedStringArray(["Game spec root must be a JSON object: %s" % path]))
		return false
	return build_spec(parsed)


func build_spec(spec: Dictionary) -> bool:
	var errors := validate_spec(spec)
	if not errors.is_empty():
		_fail(errors)
		return false
	_clear_level()
	level_data = spec.duplicate(true)
	var spawn: Dictionary = level_data["spawn"]
	spawn_position = _vector3(spawn["position"])
	spawn_rotation_degrees = _vector3(spawn.get("rotation_degrees", [0, 0, 0]))
	total_collectible_value = 0
	for object_data: Dictionary in level_data["objects"]:
		_build_object(object_data)
	level_loaded.emit(level_data)
	level_built.emit(spawn_position)
	return true


func validate_spec(data: Dictionary) -> PackedStringArray:
	var errors := PackedStringArray()
	var version: Variant = data.get("version")
	if not _is_number(version) or int(version) != SUPPORTED_VERSION or float(version) != SUPPORTED_VERSION:
		errors.append("version must be %d" % SUPPORTED_VERSION)

	_validate_named_section(data, "game", ["title", "objective", "completion_message"], errors)
	_validate_number_section(data, "player", [
		"walk_speed", "sprint_speed", "acceleration", "deceleration", "air_control",
		"turn_speed", "gravity", "jump_velocity",
	], errors)
	_validate_number_section(data, "camera", ["distance", "fov", "initial_pitch_degrees"], errors)

	if not data.has("spawn") or typeof(data["spawn"]) != TYPE_DICTIONARY:
		errors.append("spawn must be an object")
	else:
		_validate_transform(data["spawn"], "spawn", errors)
	if not data.has("objects") or typeof(data["objects"]) != TYPE_ARRAY:
		errors.append("objects must be an array")
		return errors

	var id_types: Dictionary = {}
	var goal_count := 0
	for index in data["objects"].size():
		var value: Variant = data["objects"][index]
		var prefix := "objects[%d]" % index
		if typeof(value) != TYPE_DICTIONARY:
			errors.append("%s must be an object" % prefix)
			continue
		var object_data: Dictionary = value
		var object_id := str(object_data.get("id", ""))
		var object_type := str(object_data.get("type", ""))
		if object_id.is_empty():
			errors.append("%s.id must be a non-empty string" % prefix)
		elif id_types.has(object_id):
			errors.append("%s.id duplicates '%s'" % [prefix, object_id])
		else:
			id_types[object_id] = object_type
		if object_type not in SUPPORTED_TYPES:
			errors.append("%s.type '%s' is unsupported" % [prefix, object_type])
		elif object_type == "goal":
			goal_count += 1
		if not object_data.has("transform") or typeof(object_data["transform"]) != TYPE_DICTIONARY:
			errors.append("%s.transform must be an object" % prefix)
		else:
			_validate_transform(object_data["transform"], "%s.transform" % prefix, errors)
		_validate_vector(object_data.get("size"), "%s.size" % prefix, errors, true)
		var color_value: Variant = object_data.get("color")
		if typeof(color_value) != TYPE_STRING or not Color.html_is_valid(str(color_value)):
			errors.append("%s.color must be an HTML color string" % prefix)
		if object_type == "moving_platform":
			_validate_movement(object_data.get("movement"), "%s.movement" % prefix, errors)
		elif object_type == "collectible":
			var item_value: Variant = object_data.get("value", 1)
			if not _is_integer_number(item_value) or int(item_value) <= 0:
				errors.append("%s.value must be a positive integer" % prefix)
		elif object_type in ["door", "goal"]:
			_validate_requirements(object_data.get("requirements", {}), "%s.requirements" % prefix, errors)

	for index in data["objects"].size():
		var value: Variant = data["objects"][index]
		if typeof(value) != TYPE_DICTIONARY:
			continue
		var object_data: Dictionary = value
		if str(object_data.get("type", "")) not in ["door", "goal"]:
			continue
		var requirements: Variant = object_data.get("requirements", {})
		if typeof(requirements) != TYPE_DICTIONARY:
			continue
		for switch_id: Variant in requirements.get("switches", []):
			if typeof(switch_id) == TYPE_STRING and id_types.get(str(switch_id)) != "switch":
				errors.append("objects[%d].requirements references unknown switch '%s'" % [index, switch_id])
	if goal_count == 0:
		errors.append("objects must contain at least one goal")
	return errors


func get_spawn_transform() -> Transform3D:
	return Transform3D(Basis.from_euler(spawn_rotation_degrees * PI / 180.0), spawn_position)


func get_object(object_id: StringName) -> Node3D:
	return objects_by_id.get(object_id) as Node3D


func get_requirements(object_id: StringName) -> Dictionary:
	var node := get_object(object_id)
	if node != null:
		var value: Variant = node.get("requirements")
		if typeof(value) == TYPE_DICTIONARY:
			return value
	return {}


func requirements_met(requirements: Dictionary, collectibles: int, switches: Dictionary) -> bool:
	if collectibles < int(requirements.get("collectibles", 0)):
		return false
	for switch_id: Variant in requirements.get("switches", []):
		if not switches.has(str(switch_id)):
			return false
	return true


func update_doors(collectibles: int, switches: Dictionary) -> void:
	for node: Node in get_tree().get_nodes_in_group("door"):
		var door := node as WhiteboxDoor
		if door != null:
			door.set_open(requirements_met(door.requirements, collectibles, switches))


func _build_object(data: Dictionary) -> void:
	var object_type: String = data["type"]
	var object_id := StringName(data["id"])
	var transform_data: Dictionary = data["transform"]
	var object_position := _vector3(transform_data["position"])
	var rotation := _vector3(transform_data.get("rotation_degrees", [0, 0, 0]))
	var object_size := _vector3(data["size"])
	var color := Color.from_string(data["color"], Color.WHITE)
	var node: Node3D
	match object_type:
		"static_box", "ramp":
			node = _create_static_box(object_id, object_type, object_size, color)
		"moving_platform":
			var moving_platform := MovingPlatformScript.new()
			var movement: Dictionary = data["movement"]
			moving_platform.configure(
				object_id, object_size, color, object_position,
				_vector3(movement["offset"]), float(movement["duration"])
			)
			node = moving_platform
		"hazard":
			var hazard := HazardZoneScript.new()
			hazard.configure(object_id, object_size, color)
			hazard.actor_entered.connect(_on_hazard_entered)
			node = hazard
		"collectible":
			var collectible := CollectibleScript.new()
			var value := int(data.get("value", 1))
			collectible.configure(object_id, object_size, color, value)
			collectible.collected.connect(_on_collectible_entered)
			total_collectible_value += value
			node = collectible
		"switch":
			var switch_zone := SwitchScript.new()
			switch_zone.configure(object_id, object_size, color)
			switch_zone.activated.connect(_on_switch_entered)
			node = switch_zone
		"door":
			var door := DoorScript.new()
			door.configure(object_id, object_size, color, data.get("requirements", {}))
			node = door
		"goal":
			var goal := GoalZoneScript.new()
			goal.configure(object_id, object_size, color, data.get("requirements", {}))
			goal.actor_entered.connect(_on_goal_entered)
			node = goal
		"marker":
			node = _create_marker(object_id, object_size, color)

	if object_type != "moving_platform":
		node.position = object_position
	node.rotation_degrees = rotation
	add_child(node)
	objects_by_id[object_id] = node


func _create_static_box(
	object_id: StringName, object_type: String, size: Vector3, color: Color
) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = str(object_id)
	body.set_meta("object_id", str(object_id))
	body.set_meta("object_type", object_type)
	body.set_meta("size", size)
	body.set_meta("color", color)
	body.add_to_group("whitebox_object")
	body.add_to_group(object_type)
	var mesh_instance := MeshInstance3D.new()
	var box_mesh := BoxMesh.new()
	box_mesh.size = size
	mesh_instance.mesh = box_mesh
	mesh_instance.material_override = WhiteboxNodeSetup.material(color)
	body.add_child(mesh_instance)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	return body


func _create_marker(object_id: StringName, size: Vector3, color: Color) -> Node3D:
	var marker := Node3D.new()
	marker.name = str(object_id)
	marker.set_meta("object_id", str(object_id))
	marker.set_meta("object_type", "marker")
	marker.set_meta("size", size)
	marker.set_meta("color", color)
	marker.add_to_group("whitebox_object")
	marker.add_to_group("marker")
	var mesh_instance := MeshInstance3D.new()
	var box_mesh := BoxMesh.new()
	box_mesh.size = size
	mesh_instance.mesh = box_mesh
	mesh_instance.material_override = WhiteboxNodeSetup.material(color)
	marker.add_child(mesh_instance)
	return marker


func _validate_named_section(
	data: Dictionary, section: String, keys: Array, errors: PackedStringArray
) -> void:
	if not data.has(section) or typeof(data[section]) != TYPE_DICTIONARY:
		errors.append("%s must be an object" % section)
		return
	for key: String in keys:
		var value: Variant = data[section].get(key)
		if typeof(value) != TYPE_STRING or str(value).strip_edges().is_empty():
			errors.append("%s.%s must be a non-empty string" % [section, key])


func _validate_number_section(
	data: Dictionary, section: String, keys: Array, errors: PackedStringArray
) -> void:
	if not data.has(section) or typeof(data[section]) != TYPE_DICTIONARY:
		errors.append("%s must be an object" % section)
		return
	for key: String in keys:
		if not _is_number(data[section].get(key)):
			errors.append("%s.%s must be a number" % [section, key])


func _validate_transform(value: Dictionary, prefix: String, errors: PackedStringArray) -> void:
	_validate_vector(value.get("position"), "%s.position" % prefix, errors)
	if value.has("rotation_degrees"):
		_validate_vector(value["rotation_degrees"], "%s.rotation_degrees" % prefix, errors)


func _validate_movement(value: Variant, label: String, errors: PackedStringArray) -> void:
	if typeof(value) != TYPE_DICTIONARY:
		errors.append("%s must be an object" % label)
		return
	_validate_vector(value.get("offset"), "%s.offset" % label, errors)
	if not _is_number(value.get("duration")) or float(value.get("duration", 0.0)) <= 0.0:
		errors.append("%s.duration must be greater than zero" % label)


func _validate_requirements(value: Variant, label: String, errors: PackedStringArray) -> void:
	if typeof(value) != TYPE_DICTIONARY:
		errors.append("%s must be an object" % label)
		return
	var collectible_count: Variant = value.get("collectibles", 0)
	if not _is_integer_number(collectible_count) or int(collectible_count) < 0:
		errors.append("%s.collectibles must be a non-negative integer" % label)
	var switches: Variant = value.get("switches", [])
	if typeof(switches) != TYPE_ARRAY:
		errors.append("%s.switches must be an array" % label)
		return
	for switch_id: Variant in switches:
		if typeof(switch_id) != TYPE_STRING or str(switch_id).is_empty():
			errors.append("%s.switches must contain non-empty strings" % label)
			return


func _validate_vector(
	value: Variant, label: String, errors: PackedStringArray, positive := false
) -> void:
	if typeof(value) != TYPE_ARRAY or value.size() != 3:
		errors.append("%s must be an array of three numbers" % label)
		return
	for component: Variant in value:
		if not _is_number(component):
			errors.append("%s must contain only numbers" % label)
			return
		if positive and float(component) <= 0.0:
			errors.append("%s components must be greater than zero" % label)
			return


func _is_number(value: Variant) -> bool:
	return typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT


func _is_integer_number(value: Variant) -> bool:
	return _is_number(value) and is_equal_approx(float(value), float(int(value)))


func _vector3(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func _clear_level() -> void:
	for object_node: Node in objects_by_id.values():
		remove_child(object_node)
		object_node.queue_free()
	objects_by_id.clear()
	total_collectible_value = 0


func _fail(errors: PackedStringArray) -> void:
	for error: String in errors:
		push_error("WhiteboxWorldBuilder: %s" % error)
	build_failed.emit(errors)


func _on_hazard_entered(actor: Node3D, hazard_id: StringName) -> void:
	hazard_entered.emit(actor, hazard_id)


func _on_collectible_entered(actor: Node3D, collectible_id: StringName, value: int) -> void:
	collectible_entered.emit(actor, collectible_id, value)


func _on_switch_entered(actor: Node3D, switch_id: StringName) -> void:
	switch_entered.emit(actor, switch_id)


func _on_goal_entered(actor: Node3D, goal_id: StringName) -> void:
	goal_entered.emit(actor, goal_id)
