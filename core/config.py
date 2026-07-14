# ============================================================
#  core/config.py — carrega config + personalidade e monta o system prompt
# ============================================================
import json
import os
from dataclasses import dataclass, field, fields

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_JSON    = os.path.join(BASE_DIR, "config", "config.json")
CONFIG_EXAMPLE = os.path.join(BASE_DIR, "config", "config.example.json")
PERS_JSON      = os.path.join(BASE_DIR, "config", "personalidade.json")


@dataclass
class Config:
    model: str            = "qwen3:8b"
    ollama_host: str      = "http://localhost:11434"
    num_ctx: int          = 8192
    temperature: float    = 0.4
    workdir: str          = "."
    confirm_commands: bool = True
    max_tool_chars: int   = 12000
    discord_token: str    = ""
    owner_discord_id: int = 0
    godot_bin: str        = ""
    mcp_servers: dict     = field(default_factory=dict)


def load_config(path: str = CONFIG_JSON) -> Config:
    """Carrega config.json (ou o .example se ainda não existir)."""
    src = path if os.path.exists(path) else CONFIG_EXAMPLE
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    known = {fl.name for fl in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


def load_personalidade() -> dict:
    with open(PERS_JSON, encoding="utf-8") as f:
        return json.load(f)


def build_system_prompt(cfg: Config) -> str:
    """Junta a personalidade + guia de ferramentas + memória de longo prazo."""
    from core import longmemory
    pers = load_personalidade()
    guia = (
        "\n\nFERRAMENTAS DISPONÍVEIS: read_file (ler arquivo), list_dir (listar pasta), "
        "search_code (buscar texto/regex no código), write_file (criar/editar arquivo), "
        "run_command (rodar comando de shell), check_godot_syntax (valida um script .gd "
        "rodando o Godot de verdade — use depois de escrever QUALQUER script GDScript, e "
        "corrija os erros reportados antes de considerar terminado), godot_project_info "
        "(resume o project.godot: versão, cena principal, autoloads e inputs — use ANTES de "
        "mexer num projeto Godot) e lembrar (guarda um fato na sua memória de longo prazo, "
        "que vale pra sempre em qualquer conversa). SEMPRE use as ferramentas para inspecionar "
        "o código REAL antes de responder — nunca invente o conteúdo de um arquivo. Quando o "
        "Ramon te contar uma preferência, decisão ou convenção que valha pra sempre, use "
        "'lembrar' pra não esquecer.\n"
        f"Diretório do projeto atual: {os.path.abspath(cfg.workdir)}"
    )
    return pers["system"].strip() + guia + longmemory.texto_para_prompt()
