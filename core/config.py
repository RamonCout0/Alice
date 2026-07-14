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
    pasta_referencia: str = ""   # projeto de referência que a Alice pode LER (não editar)
    max_tool_rounds: int  = 40   # teto de rodadas de ferramenta por mensagem (anti-loop)
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
        "search_code (buscar texto/regex no código), write_file (criar arquivo NOVO ou "
        "reescrever inteiro), editar_arquivo (troca CIRÚRGICA de um trecho — USE ESTE pra "
        "mudanças pequenas num arquivo existente, tipo corrigir uma linha ou adicionar uma "
        "const; nunca reescreva um arquivo grande inteiro só pra mudar pouca coisa), "
        "run_command (rodar comando de shell), check_godot_syntax (valida um script .gd "
        "rodando o Godot de verdade — use depois de escrever QUALQUER script GDScript, e "
        "corrija os erros reportados antes de considerar terminado), godot_project_info "
        "(resume o project.godot: versão, cena principal, autoloads e inputs — use ANTES de "
        "mexer num projeto Godot), godot_rodar (RODA o jogo/uma cena de verdade em headless e "
        "reporta ERROS DE RUNTIME que a sintaxe não pega), godot_screenshot (roda e RENDERIZA "
        "a imagem do jogo pra você VER o resultado visual) e lembrar (guarda um fato na sua "
        "memória de longo prazo, que vale pra sempre em qualquer conversa), buscar_padrao "
        "(pega BLOCOS DE CÓDIGO PRONTOS e corretos da biblioteca Godot 4.7 pra encaixar tipo "
        "Lego), listar_padroes e salvar_padrao. MÉTODO LEGO — obrigatório pra GDScript: ANTES "
        "de escrever qualquer código Godot do zero, chame buscar_padrao descrevendo o que "
        "precisa e ADAPTE o bloco que vier (troque nomes/valores), em vez de inventar. Isso "
        "evita erro e sintaxe antiga. Só escreva do zero se buscar_padrao não trouxer nada útil. "
        "Fluxo Godot ideal: buscar_padrao → adaptar com write_file/editar_arquivo → "
        "check_godot_syntax → godot_rodar (pega erro de runtime) → godot_screenshot "
        "(conferir o visual) → corrigir e repetir. SEMPRE use as ferramentas para inspecionar "
        "o código REAL antes de responder — nunca invente o conteúdo de um arquivo. Quando o "
        "Ramon te contar uma preferência, decisão ou convenção que valha pra sempre, use "
        "'lembrar' pra não esquecer.\n"
        f"Diretório do projeto atual (onde você CRIA/EDITA): {os.path.abspath(cfg.workdir)}"
    )
    ref = ""
    if cfg.pasta_referencia:
        ref = (
            "\n\nMODO REPRODUÇÃO: existe um projeto de REFERÊNCIA que você pode LER "
            "(mas NUNCA editar) com as ferramentas ler_referencia (ler arquivo) e "
            "listar_referencia (listar pasta). Seu trabalho é reproduzir — e MELHORAR "
            "mecanicamente — esse projeto dentro do seu diretório atual. Método: "
            "listar_referencia pra mapear a estrutura → ler_referencia de cada arquivo "
            "→ recriar o equivalente com write_file no seu diretório → check_godot_syntax "
            "→ godot_rodar → godot_screenshot → corrigir. Comece pelos autoloads/Managers "
            "(tudo depende deles) e só então arenas e entidades. Corrija erros de LÓGICA "
            "que encontrar no original em vez de copiar cegamente.\n"
            f"Pasta de referência (só leitura): {os.path.abspath(cfg.pasta_referencia)}"
        )
    return pers["system"].strip() + guia + ref + longmemory.texto_para_prompt()
