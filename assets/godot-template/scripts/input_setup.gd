class_name InputSetup
extends RefCounted

## Installs default keyboard, mouse, and gamepad bindings at runtime.

const DEFAULT_DEADZONE := 0.2


static func ensure_default_actions() -> void:
	_ensure_action(&"move_left")
	_ensure_action(&"move_right")
	_ensure_action(&"move_forward")
	_ensure_action(&"move_back")
	_ensure_action(&"jump")
	_ensure_action(&"sprint")
	_ensure_action(&"look_left")
	_ensure_action(&"look_right")
	_ensure_action(&"look_up")
	_ensure_action(&"look_down")
	_ensure_action(&"toggle_mouse_capture")

	_add_key(&"move_left", KEY_A)
	_add_key(&"move_right", KEY_D)
	_add_key(&"move_forward", KEY_W)
	_add_key(&"move_back", KEY_S)
	_add_key(&"jump", KEY_SPACE)
	_add_key(&"sprint", KEY_SHIFT)
	_add_key(&"toggle_mouse_capture", KEY_ESCAPE)

	_add_joy_axis(&"move_left", JOY_AXIS_LEFT_X, -1.0)
	_add_joy_axis(&"move_right", JOY_AXIS_LEFT_X, 1.0)
	_add_joy_axis(&"move_forward", JOY_AXIS_LEFT_Y, -1.0)
	_add_joy_axis(&"move_back", JOY_AXIS_LEFT_Y, 1.0)
	_add_joy_button(&"jump", JOY_BUTTON_A)
	_add_joy_button(&"sprint", JOY_BUTTON_LEFT_STICK)
	_add_joy_axis(&"look_left", JOY_AXIS_RIGHT_X, -1.0)
	_add_joy_axis(&"look_right", JOY_AXIS_RIGHT_X, 1.0)
	_add_joy_axis(&"look_up", JOY_AXIS_RIGHT_Y, -1.0)
	_add_joy_axis(&"look_down", JOY_AXIS_RIGHT_Y, 1.0)


static func _ensure_action(action: StringName) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action, DEFAULT_DEADZONE)


static func _add_key(action: StringName, keycode: int) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = keycode
	_add_event_if_missing(action, event)


static func _add_joy_button(action: StringName, button_index: int) -> void:
	var event := InputEventJoypadButton.new()
	event.button_index = button_index
	_add_event_if_missing(action, event)


static func _add_joy_axis(action: StringName, axis: int, axis_value: float) -> void:
	var event := InputEventJoypadMotion.new()
	event.axis = axis
	event.axis_value = axis_value
	_add_event_if_missing(action, event)


static func _add_event_if_missing(action: StringName, candidate: InputEvent) -> void:
	for existing: InputEvent in InputMap.action_get_events(action):
		if existing.is_match(candidate, true):
			return
	InputMap.action_add_event(action, candidate)
