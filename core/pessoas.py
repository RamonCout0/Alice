# ============================================================
#  core/pessoas.py — o que a Alice sabe sobre CADA PESSOA que fala com ela
#
#  Parte "convivência" da NAVI GM: apelido, poucos fatos duradouros, quando
#  falaram pela última vez. Fica em estado_pessoas.json (ignorado pelo git).
#  Tudo é pequeno de propósito: vira uma linha de contexto por mensagem, não
#  um dossiê — e a pessoa pode ver (!quem) e apagar (!esquecer) o que há dela.
# ============================================================
import json
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE_DIR, "estado_pessoas.json")

MAX_FATOS = 8
APRENDER_A_CADA = 6          # a cada N falas da pessoa, tenta extrair fatos
DIAS_SAUDADE = 3             # sumiu por esse tempo? ela comenta na volta


def _load() -> dict:
    if not os.path.exists(PATH):
        return {}
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(d: dict):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _nova(nome: str) -> dict:
    return {"nome": nome, "apelido": "", "fatos": [], "msgs": 0,
            "primeiro": time.time(), "ultimo": 0.0}


def registrar_contato(uid: int, nome: str) -> dict:
    """Marca que a pessoa falou agora. Devolve a ficha JÁ ATUALIZADA mais as
    chaves transitórias 'primeira_vez' e 'dias_ausente' (do contato anterior)."""
    d = _load()
    p = d.get(str(uid)) or _nova(nome)
    primeira = p["msgs"] == 0
    dias = (time.time() - p["ultimo"]) / 86400 if p["ultimo"] else 0.0
    p["nome"] = nome
    p["msgs"] += 1
    p["ultimo"] = time.time()
    d[str(uid)] = p
    _save(d)
    return {**p, "primeira_vez": primeira, "dias_ausente": dias}


def nome_para(p: dict) -> str:
    return p.get("apelido") or p.get("nome") or "alguém"


def contexto(p: dict) -> str:
    """Uma linha curta sobre quem está falando — anexada à mensagem, não ao system."""
    partes = []
    if p.get("primeira_vez"):
        partes.append("primeira vez que fala com você")
    elif p.get("dias_ausente", 0) >= DIAS_SAUDADE:
        partes.append(f"não aparecia há {int(p['dias_ausente'])} dias")
    if p.get("apelido"):
        partes.append(f"gosta de ser chamado de {p['apelido']}")
    if p.get("fatos"):
        partes.append("você sabe que: " + "; ".join(p["fatos"][-4:]))
    return f"(sobre {p.get('nome', 'ela')}: " + ", ".join(partes) + ")" if partes else ""


def definir_apelido(uid: int, apelido: str) -> bool:
    d = _load()
    if str(uid) not in d:
        return False
    d[str(uid)]["apelido"] = apelido.strip()[:30]
    _save(d)
    return True


def adicionar_fatos(uid: int, fatos: list[str]) -> int:
    d = _load()
    p = d.get(str(uid))
    if not p:
        return 0
    novos = 0
    existentes = {f.lower() for f in p["fatos"]}
    for f in fatos:
        f = f.strip().rstrip(".")[:120]
        if len(f) > 3 and f.lower() not in existentes:
            p["fatos"].append(f)
            existentes.add(f.lower())
            novos += 1
    p["fatos"] = p["fatos"][-MAX_FATOS:]
    _save(d)
    return novos


def ver(uid: int) -> dict | None:
    return _load().get(str(uid))


def esquecer(uid: int) -> bool:
    d = _load()
    if str(uid) in d:
        del d[str(uid)]
        _save(d)
        return True
    return False


# ------------------------------------------------------------------ aprender
_PROMPT_EXTRAIR = (
    "Das falas abaixo, extraia no MÁXIMO 2 fatos duradouros e inofensivos sobre a pessoa "
    "(gostos, projetos, hobbies, o que estuda ou faz, jeito de ser). IGNORE saúde, política, "
    "religião, dinheiro, endereço, dados de contato e qualquer coisa íntima ou de terceiros. "
    "Só fatos que ela afirmou sobre si mesma, nada deduzido. Cada fato: frase curta em "
    "português, 3ª pessoa omitida (ex: 'curte Godot', 'estuda ADS'). "
    'Responda SOMENTE JSON: {"fatos": ["..."]}. Se não houver nada, {"fatos": []}.'
)


def extrair_fatos(client, modelo: str, falas: list[str], keep_alive: str = "10m") -> list[str]:
    """Uma chamada curta ao modelo (bloqueante) que devolve fatos novos. Nunca levanta."""
    try:
        r = client.chat(
            model=modelo,
            messages=[{"role": "system", "content": _PROMPT_EXTRAIR},
                      {"role": "user", "content": "\n".join(f"- {f}" for f in falas)}],
            format="json", think=False, keep_alive=keep_alive,
            options={"temperature": 0, "num_predict": 100, "num_ctx": 2048},
        )
        dados = json.loads(r["message"]["content"])
        fatos = dados.get("fatos", [])
        return [str(f) for f in fatos][:2] if isinstance(fatos, list) else []
    except Exception:
        return []
