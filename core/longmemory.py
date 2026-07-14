# ============================================================
#  core/longmemory.py — memória de LONGO PRAZO da Alice
#
#  Diferente do histórico de conversa (que é por sessão), aqui ficam FATOS
#  que a Alice aprende e devem valer PRA SEMPRE, em qualquer conversa:
#  preferências do Ramon, decisões de projeto, convenções de código, etc.
#
#  É isso que faz ela "ficar mais inteligente com o tempo": tudo o que está
#  aqui é injetado no system prompt de toda nova conversa. A própria Alice
#  alimenta isso pela ferramenta `lembrar(...)`, e o Ramon pode editar na UI.
# ============================================================
import json
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM_PATH = os.path.join(BASE_DIR, "memoria_longa.json")


def carregar() -> list[dict]:
    """Lista de fatos: [{'texto': str, 'quando': iso, 'tag': str}]."""
    if not os.path.exists(MEM_PATH):
        return []
    try:
        with open(MEM_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _salvar(fatos: list[dict]):
    with open(MEM_PATH, "w", encoding="utf-8") as f:
        json.dump(fatos, f, ensure_ascii=False, indent=2)


def adicionar(texto: str, tag: str = "geral") -> bool:
    """Guarda um fato novo. Ignora duplicatas (mesmo texto). Retorna True se guardou."""
    texto = (texto or "").strip()
    if not texto:
        return False
    fatos = carregar()
    if any(f["texto"].strip().lower() == texto.lower() for f in fatos):
        return False
    fatos.append({"texto": texto, "tag": tag or "geral",
                  "quando": time.strftime("%Y-%m-%d %H:%M")})
    _salvar(fatos)
    return True


def remover(indice: int) -> bool:
    fatos = carregar()
    if 0 <= indice < len(fatos):
        fatos.pop(indice)
        _salvar(fatos)
        return True
    return False


def definir_todos(fatos: list[dict]):
    """Substitui a memória inteira (usado quando o Ramon edita pela UI)."""
    _salvar(fatos)


def texto_para_prompt() -> str:
    """Bloco formatado pra injetar no system prompt. Vazio se não há nada."""
    fatos = carregar()
    if not fatos:
        return ""
    linhas = [f"• [{f.get('tag', 'geral')}] {f['texto']}" for f in fatos]
    return ("\n\nMEMÓRIA DE LONGO PRAZO (coisas que você já aprendeu e deve "
            "sempre lembrar — use quando forem relevantes):\n" + "\n".join(linhas))
