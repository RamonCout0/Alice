# ============================================================
#  core/biblioteca.py — biblioteca de PADRÕES (blocos "Lego") de Godot 4.7
#
#  A ideia: em vez de pedir pra um modelo pequeno RACIOCINAR GDScript do zero
#  (onde ele erra), damos blocos de código PRONTOS e CORRETOS pra ele buscar
#  e ADAPTAR. Modelo pequeno é bom em "pega o template certo e encaixa".
#
#  A Alice cresce com o tempo: pode salvar novos padrões validados aqui.
# ============================================================
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_PATH = os.path.join(BASE_DIR, "conhecimento", "godot_4.json")


def carregar() -> dict:
    if not os.path.exists(LIB_PATH):
        return {"versao_alvo": "Godot 4.7", "padroes": []}
    try:
        with open(LIB_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"versao_alvo": "Godot 4.7", "padroes": []}


def _salvar(dados: dict):
    os.makedirs(os.path.dirname(LIB_PATH), exist_ok=True)
    with open(LIB_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def _termos(texto: str) -> list[str]:
    return [t for t in re.findall(r"\w+", (texto or "").lower()) if len(t) > 2]


def buscar(consulta: str, limite: int = 3) -> list[dict]:
    """Ranqueia os padrões por sobreposição de palavras com título/uso/tags."""
    padroes = carregar().get("padroes", [])
    termos = _termos(consulta)
    if not termos:
        return []

    def score(p: dict) -> int:
        alvo = " ".join([
            p.get("titulo", ""), p.get("quando_usar", ""),
            " ".join(p.get("tags", [])), p.get("id", ""),
        ]).lower()
        return sum(alvo.count(t) for t in termos)

    ranqueados = sorted(padroes, key=score, reverse=True)
    return [p for p in ranqueados if score(p) > 0][:limite]


def listar() -> list[tuple[str, str]]:
    return [(p.get("id", "?"), p.get("titulo", "?")) for p in carregar().get("padroes", [])]


def adicionar(titulo: str, quando_usar: str, codigo: str,
              tags: list[str] | None = None, notas: str = "") -> bool:
    """Guarda um novo padrão validado na biblioteca (a Alice fica mais capaz)."""
    dados = carregar()
    pid = re.sub(r"\W+", "_", (titulo or "").lower()).strip("_") or "padrao"
    if any(p.get("id") == pid for p in dados["padroes"]):
        return False
    dados["padroes"].append({
        "id": pid, "titulo": titulo, "quando_usar": quando_usar,
        "tags": tags or [], "codigo": codigo, "notas": notas,
    })
    _salvar(dados)
    return True
