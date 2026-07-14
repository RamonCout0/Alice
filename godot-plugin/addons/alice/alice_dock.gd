@tool
extends VBoxContainer

# Dock da Alice dentro do editor. É só a "cara": manda a sua mensagem + o
# contexto do editor (script aberto / nó selecionado) para o servidor Python
# da Alice (que roda o Ollama e as ferramentas), e mostra a resposta.
#
# Precisa do servidor rodando:  python -m frontends.webui   (porta 7861)

const URL := "http://127.0.0.1:7861/ask"

var editor  # EditorInterface (setado pelo plugin)
var _http: HTTPRequest
var _log: RichTextLabel
var _entrada: LineEdit
var _btn: Button


func _init() -> void:
	name = "Alice"


func _ready() -> void:
	custom_minimum_size = Vector2(280, 0)
	add_theme_constant_override("separation", 6)

	var titulo := Label.new()
	titulo.text = "🤖 Alice"
	add_child(titulo)

	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_following = true
	_log.selection_enabled = true
	_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(_log)

	var linha := HBoxContainer.new()
	add_child(linha)

	_entrada = LineEdit.new()
	_entrada.placeholder_text = "fala com a Alice…"
	_entrada.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_entrada.text_submitted.connect(_on_submit)
	linha.add_child(_entrada)

	_btn = Button.new()
	_btn.text = "enviar"
	_btn.pressed.connect(_on_enviar)
	linha.add_child(_btn)

	_http = HTTPRequest.new()
	_http.timeout = 600.0
	add_child(_http)
	_http.request_completed.connect(_on_resposta)

	_msg("alice", "Oi! Tô ligada no editor. Me pede algo do projeto — eu vejo o script que você tem aberto. (preciso do servidor: python -m frontends.webui)")


func _on_submit(_t: String) -> void:
	_on_enviar()


func _on_enviar() -> void:
	var msg := _entrada.text.strip_edges()
	if msg == "":
		return
	_msg("você", msg)
	_entrada.text = ""
	_set_ocupado(true)
	var corpo := JSON.stringify({"msg": msg, "contexto": _contexto()})
	var err := _http.request(URL, ["Content-Type: application/json"], HTTPClient.METHOD_POST, corpo)
	if err != OK:
		_set_ocupado(false)
		_msg("erro", "não consegui falar com o servidor (erro %d). A Alice está rodando na porta 7861?" % err)


func _contexto() -> String:
	var partes := []
	if editor:
		var se = editor.get_script_editor()
		if se:
			var scr = se.get_current_script()
			if scr:
				partes.append("script aberto: " + scr.resource_path)
		var sel = editor.get_selection()
		if sel:
			var nodes = sel.get_selected_nodes()
			if nodes.size() > 0:
				partes.append("nó selecionado: " + str(nodes[0].name))
	return ", ".join(partes)


func _on_resposta(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_set_ocupado(false)
	if code != 200:
		_msg("erro", "servidor respondeu %d (a Alice está rodando na porta 7861?)" % code)
		return
	var data = JSON.parse_string(body.get_string_from_utf8())
	if typeof(data) != TYPE_DICTIONARY:
		_msg("erro", "resposta inválida do servidor")
		return
	var ferr = data.get("ferramentas", [])
	if ferr is Array and ferr.size() > 0:
		_msg("⚙", ", ".join(ferr))
	_msg("alice", str(data.get("resposta", "")))


func _set_ocupado(v: bool) -> void:
	_btn.disabled = v
	_entrada.editable = not v
	_btn.text = "…" if v else "enviar"


func _msg(autor: String, texto: String) -> void:
	var cor := "#c084fc"
	if autor == "você":
		cor = "#8fb3ff"
	elif autor == "erro":
		cor = "#ef6b6b"
	elif autor == "⚙":
		cor = "#9fdcc0"
	_log.append_text("[color=%s][b]%s[/b][/color] %s\n\n" % [cor, autor, texto])
