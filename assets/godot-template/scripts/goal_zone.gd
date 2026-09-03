class_name WhiteboxGoalZone
extends Area3D

signal actor_entered(actor: Node3D, goal_id: StringName)

var object_id: StringName
var requirements: Dictionary = {}


func configure(
	new_id: StringName,
	zone_size: Vector3,
	zone_color: Color,
	new_requirements: Dictionary
) -> void:
	object_id = new_id
	requirements = new_requirements.duplicate(true)
	WhiteboxNodeSetup.setup_area(self, object_id, "goal", zone_size, zone_color, 0.58)
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node3D) -> void:
	if body is CharacterBody3D:
		actor_entered.emit(body, object_id)
