# ============================================================
#  core/docs.py — documentação OFICIAL do Godot 4.7 embutida
#
#  conhecimento/godot_api/ guarda a class reference inteira da engine
#  (1071 classes, gerada da tag 4.7-stable) em JSON. A Alice consulta
#  aqui como um dicionário: assinatura exata + explicação de cada método,
#  propriedade, sinal e constante. É a peça "o que existe e como chama"
#  do quebra-cabeça; a biblioteca de padrões é a peça "como se monta".
# ============================================================
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(BASE_DIR, "conhecimento", "godot_api")

_INDICE = None  # cache do índice em memória


def _indice() -> list[dict]:
    global _INDICE
    if _INDICE is None:
        caminho = os.path.join(API_DIR, "_indice.json")
        try:
            with open(caminho, encoding="utf-8") as f:
                _INDICE = json.load(f).get("classes", [])
        except (OSError, json.JSONDecodeError):
            _INDICE = []
    return _INDICE


def _entrada(nome_classe: str) -> dict | None:
    alvo = (nome_classe or "").strip().lower().lstrip("@")
    for e in _indice():
        if e["nome"].lower().lstrip("@") == alvo:
            return e
    return None


def carregar_classe(nome: str) -> dict | None:
    e = _entrada(nome)
    if e is None:
        return None
    try:
        with open(os.path.join(API_DIR, e["arquivo"]), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _cadeia_heranca(nome: str) -> str:
    cadeia, atual, vistos = [], _entrada(nome), set()
    while atual and atual.get("herda") and atual["nome"] not in vistos:
        vistos.add(atual["nome"])
        cadeia.append(atual["herda"])
        atual = _entrada(atual["herda"])
    return " < ".join(cadeia)


def _corta(texto: str, limite: int) -> str:
    t = (texto or "").strip()
    if len(t) <= limite:
        return t
    return t[:limite].rsplit(" ", 1)[0] + " (…)"


def doc_classe(nome: str, membro: str = "") -> str:
    """Formata a documentação de uma classe (visão geral) ou de membros
    específicos dela (quando `membro` é dado — casa por substring)."""
    d = carregar_classe(nome)
    if d is None:
        sugest = buscar(nome, limite=8)
        if sugest.startswith(("Nada", "Termo")):
            return (f"Classe '{nome}' não existe no Godot 4.7 (pode ser nome antigo "
                    f"do Godot 3 — ex: KinematicBody2D virou CharacterBody2D). "
                    f"Procure o nome atual com buscar_doc.")
        return f"Classe '{nome}' não existe no Godot 4.7. Talvez você queira:\n{sugest}"
    if membro:
        return _doc_membro(d, membro)

    partes = [f"# {d['nome']}" + (f" (herda {d['herda']} < {_cadeia_heranca(d['herda'])})"
                                  if d.get("herda") else "")]
    if d.get("breve"):
        partes.append(d["breve"])
    if d.get("descricao"):
        partes.append(_corta(d["descricao"], 2200))
    if d.get("propriedades"):
        linhas = [f"  {p['nome']}: {p['tipo']}"
                  + (f" = {p['padrao']}" if "padrao" in p else "")
                  for p in d["propriedades"]]
        partes.append("PROPRIEDADES:\n" + "\n".join(linhas))
    if d.get("metodos"):
        partes.append("MÉTODOS:\n" + "\n".join(f"  {m['assinatura']}" for m in d["metodos"]))
    if d.get("sinais"):
        partes.append("SINAIS:\n" + "\n".join(f"  {s['assinatura']}" for s in d["sinais"]))
    if d.get("anotacoes"):
        partes.append("ANOTAÇÕES:\n" + "\n".join(f"  {a['assinatura']}" for a in d["anotacoes"]))
    if d.get("constantes"):
        nomes = ", ".join(c["nome"] for c in d["constantes"][:60])
        extra = f" (+{len(d['constantes']) - 60})" if len(d["constantes"]) > 60 else ""
        partes.append(f"CONSTANTES: {nomes}{extra}")
    partes.append(f"→ Pra ver a explicação de um método/propriedade específico: "
                  f"godot_doc(classe='{d['nome']}', membro='nome_do_membro')")
    texto = "\n\n".join(partes)
    if len(texto) > 11000:
        texto = texto[:11000] + "\n(… lista cortada — use o parâmetro 'membro' pra focar)"
    return texto


def _doc_membro(d: dict, membro: str) -> str:
    alvo = membro.strip().lower()
    achados = []
    grupos = [("método", "metodos", "assinatura"), ("propriedade", "propriedades", "nome"),
              ("sinal", "sinais", "assinatura"), ("constante", "constantes", "nome"),
              ("anotação", "anotacoes", "assinatura"), ("construtor", "construtores", "assinatura"),
              ("operador", "operadores", "assinatura")]
    for rotulo, chave, campo in grupos:
        for item in d.get(chave, []):
            nome_item = item[campo].split("(")[0].strip().lower()
            if alvo in nome_item:
                exato = nome_item == alvo or nome_item.lstrip("@") == alvo
                achados.append((not exato, rotulo, item))
    if not achados:
        return (f"'{membro}' não existe em {d['nome']} (Godot 4.7). "
                f"Veja a lista completa com godot_doc(classe='{d['nome']}') "
                f"ou procure com buscar_doc('{membro}').")
    achados.sort(key=lambda x: x[0])
    partes = []
    for _, rotulo, item in achados[:8]:
        cab = item.get("assinatura") or (
            f"{item['nome']}: {item.get('tipo', '')}"
            + (f" = {item['padrao']}" if "padrao" in item else "")
            + (f"  (valor {item['valor']})" if "valor" in item else ""))
        corpo = _corta(item.get("desc", ""), 2600) or "(sem descrição)"
        partes.append(f"## {d['nome']} · {rotulo}\n{cab}\n{corpo}")
    return "\n\n".join(partes)[:11500]


_ERROS = None  # cache do dicionário de erros comuns


def _erros_conhecidos() -> list[dict]:
    global _ERROS
    if _ERROS is None:
        caminho = os.path.join(BASE_DIR, "conhecimento", "godot_erros.json")
        try:
            with open(caminho, encoding="utf-8") as f:
                _ERROS = json.load(f).get("erros", [])
        except (OSError, json.JSONDecodeError):
            _ERROS = []
    return _ERROS


def diagnosticar(mensagem_erro: str, limite: int = 3) -> str:
    """Casa uma mensagem de erro do Godot com o dicionário de erros comuns
    (Godot 3→4, GDScript, runtime) e devolve causa + correção + exemplo."""
    texto = (mensagem_erro or "").strip()
    if not texto:
        return ""
    achados = []
    for e in _erros_conhecidos():
        padrao = e.get("casa", "")
        try:
            casou = (re.search(padrao, texto, re.IGNORECASE) if e.get("casa_regex")
                     else padrao.lower() in texto.lower())
        except re.error:
            casou = False
        if casou:
            achados.append(e)
        if len(achados) >= limite:
            break
    if not achados:
        return ""
    partes = []
    for e in achados:
        bloco = f"CAUSA: {e['causa']}\nCORREÇÃO: {e['correcao']}"
        if e.get("exemplo"):
            bloco += f"\nEXEMPLO CERTO:\n```gdscript\n{e['exemplo']}\n```"
        partes.append(bloco)
    return "\n\n".join(partes)


def buscar(termo: str, limite: int = 12) -> str:
    """Procura `termo` em nomes de classes e de membros (métodos, propriedades,
    sinais, constantes) da API inteira. Retorna onde cada coisa mora."""
    t = (termo or "").strip().lower().lstrip("@")
    if len(t) < 2:
        return "Termo curto demais — use pelo menos 2 caracteres."
    hits = []  # (score, linha)
    for e in _indice():
        nc = e["nome"].lower().lstrip("@")
        if t in nc:
            score = 0 if nc == t else (1 if nc.startswith(t) else 3)
            hits.append((score, f"CLASSE {e['nome']} — {e['breve']}"))
        for tipo, chave in (("método", "m"), ("propriedade", "p"),
                            ("sinal", "s"), ("constante", "c")):
            for nome in e.get(chave, []):
                nm = nome.lower().lstrip("@")
                if t in nm:
                    score = 0 if nm == t else (2 if nm.startswith(t) else 4)
                    hits.append((score, f"{e['nome']}.{nome} ({tipo})"))
    if not hits:
        # busca de socorro: termos parciais (ex: "mover corpo" → "mover", "corpo")
        palavras = [w for w in re.findall(r"\w+", t) if len(w) > 2]
        if len(palavras) > 1:
            return buscar(palavras[0], limite)
        return (f"Nada na API do Godot 4.7 casa com '{termo}'. Tente o nome em inglês "
                f"(a API é em inglês: 'health' não existe, mas 'velocity' sim) ou "
                f"buscar_padrao pra achar um bloco de código pronto.")
    hits.sort(key=lambda x: (x[0], len(x[1])))
    linhas = [h[1] for h in hits[:limite]]
    extra = f"\n(+{len(hits) - limite} resultados — refine o termo)" if len(hits) > limite else ""
    return ("\n".join(linhas) + extra
            + "\n→ Detalhes: godot_doc(classe='X', membro='y')")
