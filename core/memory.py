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
