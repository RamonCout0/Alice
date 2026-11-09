# ============================================================
#  core/navi.py — o "contrato NAVI" da Alice (GM / segunda IRIS)
#
#  Tudo que define a Alice como NAVI mora aqui, sem depender de Discord,
#  site ou Ollama. Os frontends só chamam estas funções — e o app mobile do
#  Códice poderá fazer o mesmo (via backend) no futuro.
#
#    • ficha        : estado dela (fase, papel, elemento, humor) — estado_navi.json
#    • regras       : trechos do conhecimento/codice_regras.md relevantes p/ a pergunta
#    • perfil do dono: config/perfil_dono.md, SÓ para o owner (nunca p/ os outros)
# ============================================================
import json
import os
import re
import time

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHA_PATH   = os.path.join(BASE_DIR, "estado_navi.json")
REGRAS_PATH  = os.path.join(BASE_DIR, "conhecimento", "codice_regras.md")
PERFIL_PATH  = os.path.join(BASE_DIR, "config", "perfil_dono.md")

# mesmos humores do enum Humor do app Flutter (main.dart)
HUMORES = ("esperando", "lendo", "curiosa", "feliz", "confusa", "pensando")

FICHA_PADRAO = {
    "nome": "Alice",
    "papel": "GM",            # anfitriã/administradora, como a IRIS
    "elemento": "Cyber",      # exclusivo das GMs
    "fase": "adulta",         # nasce adulta (18): autonomia total, não evolui
    "humor": "esperando",
    "atualizado": None,
}


# ------------------------------------------------------------------ ficha
def carregar_ficha() -> dict:
    ficha = dict(FICHA_PADRAO)
    if os.path.exists(FICHA_PATH):
        try:
            with open(FICHA_PATH, encoding="utf-8") as f:
                ficha.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return ficha


def salvar_ficha(ficha: dict):
    ficha["atualizado"] = time.strftime("%Y-%m-%d %H:%M")
    with open(FICHA_PATH, "w", encoding="utf-8") as f:
        json.dump(ficha, f, ensure_ascii=False, indent=2)


def definir_humor(humor: str) -> bool:
    """Troca o humor se for um dos válidos. Retorna True se mudou."""
    if humor not in HUMORES:
        return False
    ficha = carregar_ficha()
    if ficha["humor"] == humor:
        return False
    ficha["humor"] = humor
    salvar_ficha(ficha)
    return True


def ficha_para_prompt() -> str:
    f = carregar_ficha()
    return (f"\n\nSUA FICHA: você é {f['nome']}, NAVI {f['papel']} de fase {f['fase']}, "
            f"elemento {f['elemento']}. Humor agora: {f['humor']}.")


# ------------------------------------------------------------------ regras do Códice
_STOP = {"para", "como", "qual", "quais", "você", "voce", "isso", "essa", "esse", "sobre",
         "tem", "uma", "com", "que", "por", "mais", "muito", "quando", "onde", "alice"}


def _tokens(texto: str) -> set[str]:
    return {t for t in re.findall(r"\w+", texto.lower()) if len(t) > 3 and t not in _STOP}


def _secoes() -> list[tuple[str, str]]:
    if not os.path.exists(REGRAS_PATH):
        return []
    with open(REGRAS_PATH, encoding="utf-8") as f:
        texto = f.read()
    partes = re.split(r"^## ", texto, flags=re.MULTILINE)[1:]
    out = []
    for p in partes:
        titulo, _, corpo = p.partition("\n")
        out.append((titulo.strip(), corpo.strip()))
    return out


def trechos_regras(pergunta: str, k: int = 2, max_chars: int = 1100) -> str:
    """Devolve as k seções do codice_regras.md mais parecidas com a pergunta
    (por palavras em comum). Vazio se nada casar — assim o 8B só carrega no
    contexto o que a mensagem realmente pede, em vez do arquivo inteiro."""
    q = _tokens(pergunta)
    if not q:
        return ""
    pontuadas = []
    for titulo, corpo in _secoes():
        pts = len(q & _tokens(titulo)) * 3 + len(q & _tokens(corpo))
        if pts:
            pontuadas.append((pts, titulo, corpo))
    pontuadas.sort(reverse=True)
    blocos = [f"[{t}] {c}" for _, t, c in pontuadas[:k]]
    return "\n".join(blocos)[:max_chars]


def com_contexto(pergunta: str) -> str:
    """Anexa à pergunta os trechos de regras relevantes (se houver)."""
    regras = trechos_regras(pergunta)
    if not regras:
        return pergunta
    return (f"(consulta ao Códice, use só se ajudar; não invente além disso:\n{regras})\n\n"
            f"{pergunta}")


# ------------------------------------------------------------------ perfil do dono
def perfil_dono_para_prompt() -> str:
    """Só deve ser chamado quando quem fala é o owner."""
    if not os.path.exists(PERFIL_PATH):
        return ""
    with open(PERFIL_PATH, encoding="utf-8") as f:
        linhas = [l.rstrip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    if not linhas:
        return ""
    return ("\n\nSOBRE QUEM ESTÁ FALANDO (é o Ramon, seu criador — use com naturalidade, "
            "sem recitar):\n" + "\n".join(linhas))
