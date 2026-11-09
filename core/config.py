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
    # --- modo leve (modelo 8B local, PC compartilhado) ---
    max_historico: int    = 0    # 0 = sem limite; N = mantém só as últimas N mensagens (fora o system)
    num_predict: int      = 0    # 0 = sem limite; N = teto de tokens por resposta
    repeat_penalty: float = 1.0  # >1 reduz repetição de frases (bom p/ resenha)
    keep_alive: str       = "10m"  # quanto tempo o modelo fica na VRAM depois do uso
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


def build_system_prompt(cfg: Config, modo: str = "agente") -> str:
    """Monta o system prompt. modo='agente' (web/plugin: personalidade completa +
    guia de ferramentas) ou modo='conversa' (Discord: só a persona leve, sem o
    despejo técnico, pra não ficar seca/repetitiva)."""
    from core import longmemory, navi
    pers = load_personalidade()
    if modo in ("gm", "gm_dono") and pers.get("persona_gm"):
        # NAVI GM (segunda IRIS). O perfil e a memória de longo prazo contêm dados
        # pessoais do Ramon, então só entram no modo 'gm_dono' — nunca p/ os outros.
        base = pers["persona_gm"].strip() + navi.ficha_para_prompt()
        if modo == "gm_dono":
            base += navi.perfil_dono_para_prompt() + longmemory.texto_para_prompt()
        return base
    if modo == "conversa" and pers.get("persona_discord"):
        return pers["persona_discord"].strip() + longmemory.texto_para_prompt()
    guia = (
        "\n\nSUAS FERRAMENTAS (agrupadas):\n"
        "• Arquivos: read_file, list_dir, search_code (grep), write_file (arquivo novo/"
        "reescrever inteiro), editar_arquivo (troca CIRÚRGICA de trecho — prefira este pra "
        "mudança pequena em arquivo existente), run_command (shell).\n"
        "• Validação Godot: godot_project_info (resumo do project.godot: versão, cena "
        "principal, autoloads, inputs), check_godot_syntax (compila um .gd de verdade), "
        "godot_rodar (executa o jogo headless e pega erro de RUNTIME), godot_screenshot "
        "(renderiza a tela pra você VER o resultado).\n"
        "• Conhecimento Godot 4.7 — suas 3 fontes locais:\n"
        "  1) buscar_padrao / listar_padroes — blocos de código PRONTOS e validados (Lego) "
        "pra adaptar em vez de inventar; salvar_padrao guarda um bloco novo que você validou.\n"
        "  2) godot_doc / buscar_doc — a DOCUMENTAÇÃO OFICIAL COMPLETA do Godot 4.7 "
        "(todas as 1071 classes) embutida: godot_doc(classe) mostra tudo que a classe tem; "
        "godot_doc(classe, membro) explica um método/propriedade/sinal com a assinatura EXATA; "
        "buscar_doc(termo) descobre em que classe algo mora (a API é em inglês).\n"
        "  3) diagnosticar_erro — cole um erro do Godot e receba causa + correção "
        "(check_godot_syntax e godot_rodar já anexam esse diagnóstico sozinhos quando reconhecem o erro).\n"
        "• Web (última opção, só quando as fontes locais não bastarem): buscar_asset_godot "
        "(Asset Library oficial), abrir_url (ler página/código cru). Cuidado: muito código da "
        "web é Godot 3 — só aproveite o que passar no check_godot_syntax.\n"
        "• Cenas (.tscn) via MCP, quando disponível: create_scene, add_node, save_scene, "
        "load_sprite, get_uid — chamam o Godot de verdade pra montar a cena, então o arquivo "
        "sai sempre no formato certo. PREFIRA ISSO a escrever .tscn à mão com write_file — "
        "texto de cena escrito à mão erra fácil (UIDs, formato de nó, ext_resource). Também "
        "há get_project_info, run_project, get_debug_output, list_projects (via MCP) que se "
        "sobrepõem às suas godot_project_info/godot_rodar locais — use as locais primeiro, "
        "essas são um plano B com outra implementação.\n"
        "• Memória: lembrar (fato permanente — preferência do Ramon, decisão de projeto).\n"
        "\nMÉTODO QUEBRA-CABEÇA — OBRIGATÓRIO pra qualquer GDScript. Você NÃO escreve código "
        "de cabeça: você MONTA com peças das suas fontes. Os passos, SEMPRE nesta ordem:\n"
        "1. godot_project_info — entenda o projeto (versão, autoloads, inputs) antes de mexer.\n"
        "2. buscar_padrao com o que precisa (ex: 'inimigo persegue player') — o bloco que vier "
        "é seu ESQUELETO; adapte nomes e valores em vez de escrever do zero.\n"
        "3. Pra CADA método/propriedade que você for usar e não veio do padrão: confirme na doc "
        "com godot_doc/buscar_doc. NUNCA chute nome ou assinatura de API — se não tem certeza "
        "de que existe, buscar_doc custa uma chamada e não erra.\n"
        "4. Escreva o script (.gd) com write_file (novo) ou editar_arquivo (mudança pontual). "
        "Pra CENA (.tscn) nova, prefira create_scene/add_node/save_scene (MCP) — só use "
        "write_file pra .tscn se o MCP não estiver disponível.\n"
        "5. check_godot_syntax no arquivo. Deu erro? Leia o diagnóstico anexado, corrija a "
        "LINHA apontada e cheque de novo. Repita até OK. (Exceção: 'Identifier not found' de "
        "um nome que está em [autoload] no project.godot é falso positivo — ignore.)\n"
        "6. godot_rodar — pega erros que só aparecem executando (null, sinal mal conectado).\n"
        "7. godot_screenshot — confira o visual quando fizer sentido.\n"
        "8. Montou um bloco novo, útil e VALIDADO que a biblioteca não tinha? salvar_padrao — "
        "é assim que você fica mais capaz com o tempo.\n"
        "Só está TERMINADO quando check_godot_syntax e godot_rodar passam sem erro.\n"
        "\nRegras de ouro:\n"
        "• SEMPRE inspecione o código REAL com as ferramentas antes de afirmar qualquer "
        "coisa sobre ele — nunca invente conteúdo de arquivo.\n"
        "• Qualquer afirmação sobre a API do Godot (o que um método recebe/retorna, se "
        "existe, como se chama) SÓ pode sair de godot_doc/buscar_doc — NUNCA da sua memória. "
        "Sua memória mistura Godot 3 com Godot 4 e erra; a doc embutida nunca erra. Isso vale "
        "até pra pergunta simples em conversa: consulte ANTES de responder.\n"
        "• Quando o Ramon te contar uma preferência ou convenção duradoura, use 'lembrar'.\n"
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
