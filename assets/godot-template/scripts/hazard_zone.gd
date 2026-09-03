class_name WhiteboxHazardZone
extends Area3D

signal actor_entered(actor: Node3D, hazard_id: StringName)

var object_id: StringName


func configure(new_id: StringName, zone_size: Vector3, zone_color: Color) -> void:
	object_id = new_id
	WhiteboxNodeSetup.setup_area(self, object_id, "hazard", zone_size, zone_color, 0.52)
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node3D) -> void:
	if body is CharacterBody3D:
		actor_entered.emit(body, object_id)
