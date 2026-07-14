# ============================================================
#  core/memory.py — persistência simples de sessões (histórico)
# ============================================================
import json
import os

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_DIR = os.path.join(BASE_DIR, "sessions")


def _path(nome: str) -> str:
    os.makedirs(SESSION_DIR, exist_ok=True)
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)
    return os.path.join(SESSION_DIR, f"{seguro}.json")


def salvar(nome: str, messages: list):
    with open(_path(nome), "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def carregar(nome: str):
    p = _path(nome)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


# ============================================================
#  Conversas persistentes (usadas pela interface web) — cada conversa é
#  um arquivo com título + timestamp + mensagens, pra dar pra listar,
#  retomar, renomear e apagar pela UI. O histórico sobrevive a reinícios.
# ============================================================
import time
import glob

CONV_DIR = os.path.join(BASE_DIR, "conversas")


def _conv_path(conv_id: str) -> str:
    os.makedirs(CONV_DIR, exist_ok=True)
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in conv_id)
    return os.path.join(CONV_DIR, f"{seguro}.json")


def novo_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def salvar_conversa(conv_id: str, messages: list, titulo: str | None = None):
    """Salva as mensagens (sem o system prompt) + metadados."""
    p = _conv_path(conv_id)
    if titulo is None:
        titulo = _titulo_auto(messages)
    dados = {
        "id": conv_id,
        "titulo": titulo,
        "atualizado": time.strftime("%Y-%m-%d %H:%M"),
        "messages": messages,
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def carregar_conversa(conv_id: str) -> dict | None:
    p = _conv_path(conv_id)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def apagar_conversa(conv_id: str) -> bool:
    p = _conv_path(conv_id)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False


def listar_conversas() -> list[dict]:
    """Metadados de todas as conversas, mais recentes primeiro."""
    os.makedirs(CONV_DIR, exist_ok=True)
    out = []
    for arq in glob.glob(os.path.join(CONV_DIR, "*.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                d = json.load(f)
            out.append({"id": d.get("id"), "titulo": d.get("titulo") or "(sem título)",
                        "atualizado": d.get("atualizado", ""),
                        "n": len(d.get("messages", []))})
        except (json.JSONDecodeError, OSError):
            continue
    out.sort(key=lambda x: x["atualizado"], reverse=True)
    return out


def _titulo_auto(messages: list) -> str:
    """Título a partir da primeira fala do usuário."""
    for m in messages:
        if m.get("role") == "user" and m.get("content"):
            t = m["content"].strip().replace("\n", " ")
            return (t[:45] + "…") if len(t) > 45 else t
    return "nova conversa"
