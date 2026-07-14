#!/usr/bin/env python3
"""Regenera conhecimento/godot_api/ a partir do código-fonte do Godot.

Uso (quando o Ramon atualizar a versão do Godot):
  1. baixe o tarball da tag correspondente, ex:
     curl -sL -o /tmp/godot.tar.gz https://github.com/godotengine/godot/archive/refs/tags/4.7-stable.tar.gz
  2. tar xzf /tmp/godot.tar.gz -C /tmp --wildcards "*/doc/classes/*.xml" "*/modules/*/doc_classes/*.xml"
  3. python3 gerar_docs_godot.py /tmp/godot-4.7-stable conhecimento/godot_api

Converte o class reference XML em JSON compacto (um arquivo por classe +
_indice.json). Mantém descrições completas e exemplos GDScript; descarta C#.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from glob import glob

SRC = sys.argv[1]      # raiz godot-4.7-stable
DEST = sys.argv[2]     # conhecimento/godot_api


def limpar(texto: str) -> str:
    """BBCode da doc -> texto simples legível (mantém código GDScript)."""
    t = texto or ""
    # blocos multi-linguagem: mantém só o gdscript
    t = re.sub(r"(?s)\[csharp[^\]]*\].*?\[/csharp\]", "", t)
    t = re.sub(r"\[/?codeblocks\]", "", t)
    t = re.sub(r"\[gdscript[^\]]*\]", "\n```gdscript", t)
    t = re.sub(r"\[/gdscript\]", "```\n", t)
    t = re.sub(r"\[codeblock[^\]]*\]", "\n```gdscript", t)
    t = re.sub(r"\[/codeblock\]", "```\n", t)
    # referências cruzadas viram nomes simples
    t = re.sub(r"\[(?:method|member|signal|constant|enum|annotation|constructor|operator|theme_item) ([^\]]+)\]", r"'\1'", t)
    t = re.sub(r"\[param ([^\]]+)\]", r"'\1'", t)
    t = re.sub(r"\[url=([^\]]*)\]([^\[]*)\[/url\]", r"\2", t)
    t = re.sub(r"\[/?(b|i|u|s|code|kbd|center|color[^\]]*|font[^\]]*|img[^\]]*|url)\]", "", t)
    t = re.sub(r"\[br\]", "\n", t)
    # [Classe] -> Classe (qualquer tag restante que pareça nome de classe/id)
    t = re.sub(r"\[([A-Za-z_@][\w@.]*)\]", r"\1", t)
    # normaliza indentação: prosa perde os tabs do XML; código (dentro de
    # cercas ```) mantém a indentação RELATIVA (essencial em GDScript)
    saida, bloco, em_codigo = [], [], False
    for l in t.splitlines():
        s = l.strip()
        if s.startswith("```"):
            if em_codigo:
                base = min((len(x) - len(x.lstrip("\t")) for x in bloco if x.strip()),
                           default=0)
                saida += [x[base:] if x.strip() else "" for x in bloco]
                bloco = []
            em_codigo = not em_codigo
            saida.append(s)
        elif em_codigo:
            bloco.append(l.rstrip())
        else:
            saida.append(s)
    saida += bloco
    t = "\n".join(saida)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def assinatura_metodo(m) -> str:
    ret = m.find("return")
    tipo_ret = ret.get("type", "void") if ret is not None else "void"
    if ret is not None and ret.get("enum"):
        tipo_ret = ret.get("enum")
    params = []
    for p in sorted(m.findall("param"), key=lambda x: int(x.get("index", 0))):
        s = f"{p.get('name')}: {p.get('enum') or p.get('type')}"
        if p.get("default") is not None:
            s += f" = {p.get('default')}"
        params.append(s)
    quali = (" " + m.get("qualifiers")) if m.get("qualifiers") else ""
    return f"{m.get('name')}({', '.join(params)}) -> {tipo_ret}{quali}"


def assinatura_sinal(s) -> str:
    params = [f"{p.get('name')}: {p.get('type')}"
              for p in sorted(s.findall("param"), key=lambda x: int(x.get("index", 0)))]
    return f"{s.get('name')}({', '.join(params)})"


def converter_classe(xml_path: str) -> dict | None:
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None
    if root.tag != "class":
        return None
    d = {
        "nome": root.get("name"),
        "herda": root.get("inherits", ""),
        "breve": limpar((root.findtext("brief_description") or "")),
        "descricao": limpar((root.findtext("description") or "")),
    }
    metodos = []
    for m in root.findall("./methods/method"):
        metodos.append({"assinatura": assinatura_metodo(m),
                        "desc": limpar(m.findtext("description") or "")})
    if metodos:
        d["metodos"] = metodos

    construtores = []
    for m in root.findall("./constructors/constructor"):
        construtores.append({"assinatura": assinatura_metodo(m),
                             "desc": limpar(m.findtext("description") or "")})
    if construtores:
        d["construtores"] = construtores

    operadores = []
    for m in root.findall("./operators/operator"):
        operadores.append({"assinatura": assinatura_metodo(m),
                           "desc": limpar(m.findtext("description") or "")})
    if operadores:
        d["operadores"] = operadores

    props = []
    for p in root.findall("./members/member"):
        item = {"nome": p.get("name"), "tipo": p.get("enum") or p.get("type", "")}
        if p.get("default") is not None:
            item["padrao"] = p.get("default")
        desc = limpar(p.text or "")
        if desc:
            item["desc"] = desc
        props.append(item)
    if props:
        d["propriedades"] = props

    sinais = []
    for s in root.findall("./signals/signal"):
        sinais.append({"assinatura": assinatura_sinal(s),
                       "desc": limpar(s.findtext("description") or "")})
    if sinais:
        d["sinais"] = sinais

    consts = []
    for c in root.findall("./constants/constant"):
        item = {"nome": c.get("name"), "valor": c.get("value", "")}
        if c.get("enum"):
            item["enum"] = c.get("enum")
        desc = limpar(c.text or "")
        if desc:
            item["desc"] = desc
        consts.append(item)
    if consts:
        d["constantes"] = consts

    anots = []
    for a in root.findall("./annotations/annotation"):
        anots.append({"assinatura": assinatura_metodo(a),
                      "desc": limpar(a.findtext("description") or "")})
    if anots:
        d["anotacoes"] = anots

    itens_tema = []
    for t in root.findall("./theme_items/theme_item"):
        itens_tema.append({"nome": t.get("name"), "tipo": t.get("type", ""),
                           "desc": limpar(t.text or "")})
    if itens_tema:
        d["itens_tema"] = itens_tema
    return d


def main():
    xmls = sorted(glob(os.path.join(SRC, "doc/classes/*.xml"))
                  + glob(os.path.join(SRC, "modules/*/doc_classes/*.xml")))
    os.makedirs(DEST, exist_ok=True)
    indice = []
    total_bytes = 0
    for x in xmls:
        d = converter_classe(x)
        if d is None or not d.get("nome"):
            continue
        nome = d["nome"]
        # nome de arquivo seguro (classes tipo "float" ou "@GDScript")
        arq = re.sub(r"[^\w@.]", "_", nome) + ".json"
        caminho = os.path.join(DEST, arq)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        total_bytes += os.path.getsize(caminho)
        indice.append({
            "nome": nome,
            "arquivo": arq,
            "herda": d.get("herda", ""),
            "breve": d.get("breve", "")[:160],
            "m": [m["assinatura"].split("(")[0] for m in d.get("metodos", [])],
            "p": [p["nome"] for p in d.get("propriedades", [])],
            "s": [s["assinatura"].split("(")[0] for s in d.get("sinais", [])],
            "c": [c["nome"] for c in d.get("constantes", [])][:400],
        })
    with open(os.path.join(DEST, "_indice.json"), "w", encoding="utf-8") as f:
        json.dump({"versao": "Godot 4.7 (4.7-stable oficial)", "classes": indice},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(indice)} classes convertidas — {total_bytes/1e6:.1f} MB de docs "
          f"+ índice {os.path.getsize(os.path.join(DEST, '_indice.json'))/1e6:.2f} MB")


if __name__ == "__main__":
    main()
