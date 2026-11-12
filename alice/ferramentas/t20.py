"""Ferramentas de mesa de Tormenta 20 — regras do `artoniana` + consulta a livros."""
from __future__ import annotations

import random
import re
from pathlib import Path

from alice import armazenamento as arm
from alice.ferramentas import artoniana_regras as art
from alice.ferramentas import ferramenta
from alice.ferramentas import rpg

TERRENOS = list(art.TERRENOS)
CLIMAS = list(art.CLIMA_NOTAS)


def formatar_rolagem(r: dict) -> str:
    partes = []
    for c in r["components"]:
        sinal = "-" if c["sign"] < 0 else "+"
        if c["type"] == "dice":
            partes.append(f"{sinal} {c['token']} {c['rolls']}")
        else:
            partes.append(f"{sinal} {c['value']}")
    corpo = " ".join(partes).lstrip("+ ").strip()
    expr = re.sub(r"\s+", "", r["expr"])
    return f"`{expr}` → {corpo} = **{r['total']}**"


def rolar_texto(texto: str) -> list[str]:
    resultados, erros = art.roll_message(texto)
    return [formatar_rolagem(r) for r in resultados] + [f"⚠️ {e}" for e in erros]


@ferramenta(
    "Rola dados de verdade (ex.: '1d20+5', '2d6+1d4-2'). SEMPRE use isto para qualquer "
    "rolagem — nunca invente um resultado de dado.",
    {"expressao": ("string", "expressão de dados, ex.: 1d20+7")}, ["expressao"])
def rolar_dados(ctx, expressao: str):
    linhas = rolar_texto(expressao)
    return "\n".join(linhas) if linhas else "não achei nenhum dado nessa expressão (use algo como 1d20+5)."


@ferramenta(
    "Clima de Tormenta 20 (p.267). acao='gerar' sorteia um clima coerente com o terreno da "
    "campanha; 'ver' mostra o atual; 'definir' fixa um clima. Gerar/definir é só para o mestre.",
    {"acao": ("string", "o que fazer", ["gerar", "ver", "definir"]),
     "clima": ("string", "só para 'definir'", CLIMAS)}, ["acao"])
def clima_t20(ctx, acao: str, clima: str = ""):
    camp = rpg.campanha(ctx.guild_id)
    if acao == "ver":
        atual = camp.get("clima")
        return (f"Clima atual: {art.rotulo(atual)}. {art.CLIMA_NOTAS.get(atual, '')}"
                if atual else "Nenhum clima definido ainda.")
    if not rpg.e_mestre(camp, ctx):
        return "só o mestre da campanha muda o clima."
    terreno = camp.get("terreno")
    if acao == "gerar":
        clima = random.choice(art.ALLOWED_CLIMES.get(terreno) or art.ALLOWED_CLIMES[None])
    elif clima not in art.CLIMA_NOTAS:
        return f"clima desconhecido. Opções: {', '.join(CLIMAS)}"
    elif terreno and clima not in art.ALLOWED_CLIMES[terreno]:
        return f"{art.rotulo(clima)} não combina com {art.rotulo(terreno)}."
    camp["clima"] = clima
    rpg.salvar(ctx.guild_id, camp)
    return f"Clima: **{art.rotulo(clima)}** (terreno: {art.rotulo(terreno)}). {art.CLIMA_NOTAS[clima]}"


@ferramenta(
    "Define o terreno da campanha e lista os elementos dele com as CDs (T20 p.264-266). "
    "Sem 'tipo', mostra o terreno atual. Definir é só para o mestre.",
    {"tipo": ("string", "terreno", TERRENOS)})
def terreno_t20(ctx, tipo: str = ""):
    camp = rpg.campanha(ctx.guild_id)
    if tipo:
        if tipo not in art.TERRENOS:
            return f"terreno desconhecido. Opções: {', '.join(TERRENOS)}"
        if not rpg.e_mestre(camp, ctx):
            return "só o mestre da campanha muda o terreno."
        camp["terreno"] = tipo
        if camp.get("clima") and camp["clima"] not in art.ALLOWED_CLIMES[tipo]:
            camp["clima"] = None
        rpg.salvar(ctx.guild_id, camp)
    tipo = camp.get("terreno")
    if not tipo:
        return "Nenhum terreno definido ainda."
    elementos = "\n".join(f"• **{n}** — {d}" for n, d in art.TERRENOS[tipo])
    return f"Terreno: **{art.rotulo(tipo)}**\n{elementos}"


@ferramenta(
    "Calcula a distância de viagem (T20 Tabela 6-4, p.270) usando o terreno e o clima da campanha.",
    {"deslocamento": ("number", "deslocamento do grupo em metros (padrão 9)"),
     "horas": ("integer", "horas de viagem (padrão 8)"),
     "marcha_forcada": ("boolean", "se estão em marcha forçada")})
def viagem_t20(ctx, deslocamento: float = 9, horas: int = 8, marcha_forcada: bool = False):
    camp = rpg.campanha(ctx.guild_id)
    horas = max(1, min(int(horas or 8), 24))
    km = art.compute_travel_distance(deslocamento, horas, camp.get("terreno"), camp.get("clima"),
                                     bool(marcha_forcada))
    extra = (" Marcha forçada: Fortitude CD 15 (+1 por hora) ou perde 1d6 PV por hora."
             if marcha_forcada else "")
    return (f"{km:g} km em {horas}h (deslocamento {deslocamento:g}m, terreno "
            f"{art.rotulo(camp.get('terreno'))}, clima {art.rotulo(camp.get('clima'))}).{extra}")


def formatar_recompensa(item: dict) -> str:
    linhas = [f"**{item['item']}** ({'escudo' if item['is_shield'] else 'armadura'}, {item['rarity']})"]
    if item["specific"]:
        linhas.append(f"Item específico — {item['specific']['preco']}: {item['specific']['descricao']}")
    for e in item["enchants"]:
        linhas.append(f"• *{e['nome']}* ({e['efeito']}): {e['descricao']}")
    linhas += [f"_{n}_" for n in item["notes"]]
    linhas.append("Rolagens: " + " · ".join(item["rolls"]))
    return "\n".join(linhas)


@ferramenta(
    "Gera uma armadura ou escudo mágico pelas tabelas do T20 (p.338-340).",
    {"raridade": ("string", "raridade do item", ["menor", "medio", "maior"]),
     "tipo": ("string", "restringe o tipo", ["armadura", "escudo"])})
def recompensa_t20(ctx, raridade: str = "medio", tipo: str = ""):
    if raridade not in art.RARIDADES:
        raridade = "medio"
    return formatar_recompensa(art.generate_magic_armor(raridade, tipo or None))


# ---------------------------------------------------------- consulta a livros
_cache_livros: dict[str, list] = {}


def _livros(pasta: str) -> dict[str, list]:
    p = Path(pasta)
    if p.is_dir():
        for arq in p.glob("*.json"):
            if arq.stem not in _cache_livros:
                _cache_livros[arq.stem] = arm.ler(arq, list) or []
    return _cache_livros


def _tokens(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", t.lower())]


def buscar_no_livro(pasta: str, consulta: str, n: int = 3) -> list[dict]:
    termos = set(_tokens(consulta))
    if not termos:
        return []
    frase = consulta.lower().strip()
    achados = []
    for livro, paginas in _livros(pasta).items():
        for pg in paginas:
            texto = pg["texto"].lower()
            pontos = sum(min(texto.count(t), 6) for t in termos)
            if frase in texto:
                pontos += 12
            if pontos:
                achados.append((pontos, livro, pg))
    achados.sort(key=lambda x: -x[0])
    return [{"livro": l, "pagina": pg["pagina"], "texto": pg["texto"]} for _, l, pg in achados[:n]]


@ferramenta(
    "Procura uma regra, magia, poder, criatura ou termo nos livros de Tormenta 20 que o dono "
    "indexou. Devolve os trechos com o número da página. Use antes de afirmar qualquer regra.",
    {"termo": ("string", "o que procurar, ex.: 'agarrar', 'Bola de Fogo', 'condição abalado'")},
    ["termo"], externa=True)
def consultar_regra(ctx, termo: str):
    achados = buscar_no_livro(ctx.cfg.pasta_livros, termo)
    if not achados:
        if not _cache_livros:
            return ("nenhum livro indexado ainda (o dono precisa rodar "
                    "`python -m alice.indexar_livro <arquivo.pdf>`). Use pesquisar_web.")
        return "não achei nos livros indexados. Tente outro termo ou pesquisar_web."
    return "\n\n".join(f"[{a['livro']} p.{a['pagina']}]\n{a['texto'][:1700]}" for a in achados)
