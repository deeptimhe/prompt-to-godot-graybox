class_name GrayboxHUD
extends CanvasLayer

var _game: Dictionary = {}
var _total_collectibles := 0
var _status_label: Label
var _timer_label: Label
var _progress_label: Label
var _complete_panel: PanelContainer
var _complete_label: Label


func configure(game_data: Dictionary, total_collectibles: int) -> void:
	_game = game_data.duplicate(true)
	_total_collectibles = total_collectibles


func _ready() -> void:
	_build_interface()


func set_elapsed(seconds: float) -> void:
	if _timer_label != null:
		_timer_label.text = "Time  %.1f s" % seconds


func set_status(message: String) -> void:
	if _status_label != null:
		_status_label.text = message


func set_progress(collected: int, active_switch_count: int) -> void:
	if _progress_label == null:
		return
	var collectible_text := "Collectibles  %d / %d" % [collected, _total_collectibles]
	_progress_label.text = "%s    Switches  %d" % [collectible_text, active_switch_count]


func show_locked_requirements(
	requirements: Dictionary, collected: int, active_switches: Dictionary
) -> void:
	var missing: Array[String] = []
	var needed_collectibles := int(requirements.get("collectibles", 0))
	if collected < needed_collectibles:
		missing.append("%d more collectible points" % (needed_collectibles - collected))
	for switch_id: Variant in requirements.get("switches", []):
		if not active_switches.has(str(switch_id)):
			missing.append("switch %s" % switch_id)
	set_status("Locked — need %s" % ", ".join(missing))


func show_completion(elapsed: float) -> void:
	if _complete_panel == null:
		return
	_complete_label.text = "%s\n%.1f s\nPress Enter / Start to restart" % [
		str(_game.get("completion_message", "Complete")), elapsed,
	]
	_complete_panel.visible = true


func hide_completion() -> void:
	if _complete_panel != null:
		_complete_panel.visible = false


func _build_interface() -> void:
	var root := Control.new()
	root.name = "HUDRoot"
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	var info := VBoxContainer.new()
	info.name = "Info"
	info.position = Vector2(18.0, 16.0)
	info.add_theme_constant_override("separation", 6)
	root.add_child(info)
	var title := Label.new()
	title.text = str(_game.get("title", "Godot Graybox"))
	title.add_theme_font_size_override("font_size", 24)
	info.add_child(title)
	_status_label = Label.new()
	_status_label.text = "Exploring"
	_status_label.add_theme_font_size_override("font_size", 18)
	info.add_child(_status_label)
	_progress_label = Label.new()
	_progress_label.add_theme_font_size_override("font_size", 16)
	info.add_child(_progress_label)
	set_progress(0, 0)
	_timer_label = Label.new()
	_timer_label.add_theme_font_size_override("font_size", 16)
	info.add_child(_timer_label)
	set_elapsed(0.0)

	var objective := Label.new()
	objective.text = str(_game.get("objective", "Reach the goal"))
	objective.position = Vector2(18.0, 148.0)
	objective.add_theme_font_size_override("font_size", 16)
	root.add_child(objective)

	var controls_panel := PanelContainer.new()
	controls_panel.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	controls_panel.position = Vector2(-520.0, -62.0)
	controls_panel.size = Vector2(1040.0, 42.0)
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color("#10141CDD")
	panel_style.corner_radius_top_left = 6
	panel_style.corner_radius_top_right = 6
	panel_style.corner_radius_bottom_left = 6
	panel_style.corner_radius_bottom_right = 6
	panel_style.content_margin_left = 10.0
	panel_style.content_margin_right = 10.0
	panel_style.content_margin_top = 7.0
	panel_style.content_margin_bottom = 7.0
	controls_panel.add_theme_stylebox_override("panel", panel_style)
	root.add_child(controls_panel)
	var controls := Label.new()
	controls.text = "WASD / left stick move · mouse / right stick look · Space / A jump · Shift / L3 sprint · R reset"
	controls.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	controls.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	controls_panel.add_child(controls)

	_complete_panel = PanelContainer.new()
	_complete_panel.set_anchors_preset(Control.PRESET_CENTER)
	_complete_panel.position = Vector2(-220.0, -90.0)
	_complete_panel.size = Vector2(440.0, 180.0)
	root.add_child(_complete_panel)
	_complete_label = Label.new()
	_complete_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_complete_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_complete_label.add_theme_font_size_override("font_size", 24)
	_complete_panel.add_child(_complete_label)
	_complete_panel.visible = false
