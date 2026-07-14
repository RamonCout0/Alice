@tool
extends EditorPlugin

# Ponto de entrada do plugin: cria o dock da Alice no editor e o liga ao
# EditorInterface (pra ela saber qual script/nó você está mexendo).

const AliceDock = preload("res://addons/alice/alice_dock.gd")

var _dock


func _enter_tree() -> void:
	_dock = AliceDock.new()
	_dock.editor = get_editor_interface()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _exit_tree() -> void:
	if _dock:
		remove_control_from_docks(_dock)
		_dock.free()
		_dock = null
