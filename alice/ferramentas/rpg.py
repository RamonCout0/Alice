"""Campanhas e sessões de RPG — estado por servidor em dados/rpg/<guild>.json.

Quem cria a campanha vira o mestre; só mestre (ou o dono) mexe no que é do
mestre. Isso é conferido aqui no código, não no prompt.
"""
from __future__ import annotations

import random
import time

from alice import armazenamento as arm
from alice import seguranca as seg
from alice.config import DADOS
from alice.ferramentas import ferramenta

DIR_RPG = DADOS / "rpg"


def _arq(guild_id: int):
    return DIR_RPG / f"{int(guild_id or 0)}.json"


def campanha(guild_id: int) -> dict:
    return arm.ler(_arq(guild_id), lambda: {
        "nome": "", "sistema": "Tormenta 20", "mestre_id": 0, "co_mestres": [],
        "alice_mestra": False, "premissa": "", "terreno": None, "clima": None,
        "personagens": {}, "npcs": [], "sessoes": [], "diario": [], "iniciativa": []})


def salvar(guild_id: int, camp: dict) -> None:
    arm.gravar(_arq(guild_id), camp)


def e_mestre(camp: dict, ctx) -> bool:
    # Com a Alice de mestra, ela usa as ferramentas de mestre no canal da mesa
    # (quem julga o pedido do jogador é a narradora, pelas regras do jogo).
    if camp.get("alice_mestra") and ctx.canal_id and ctx.canal_id == camp.get("canal_id"):
        return True
    return (ctx.nivel >= seg.DONO or ctx.user_id == camp.get("mestre_id")
            or ctx.user_id in camp.get("co_mestres", []))


def _hoje() -> str:
    return time.strftime("%Y-%m-%d")


def resumo_campanha(camp: dict, para_mestre: bool) -> str:
    if not camp["nome"]:
        return "Ainda não existe campanha neste servidor. Alguém cria com /campanha criar."
    linhas = [f"Campanha: {camp['nome']} ({camp['sistema']})",
              f"Mestre: {'Alice' if camp['alice_mestra'] else '<@%d>' % camp['mestre_id']}",
              f"Premissa: {camp['premissa'] or '—'}",
              f"Terreno: {camp['terreno'] or '—'} · Clima: {camp['clima'] or '—'}"]
    if camp["personagens"]:
        linhas.append("Personagens:")
        for uid, p in camp["personagens"].items():
            linhas.append(f"  • {p['nome']} — {p.get('raca', '?')} {p.get('classe', '?')} "
                          f"nv {p.get('nivel', 1)} · PV {p.get('pv', '?')}/{p.get('pv_max', '?')} "
                          f"· PM {p.get('pm', '?')}/{p.get('pm_max', '?')} (jogador {uid})")
    if camp["npcs"] and para_mestre:
        linhas.append("NPCs: " + "; ".join(f"{n['nome']} ({n['papel']})" for n in camp["npcs"][-12:]))
    if camp["sessoes"]:
        s = camp["sessoes"][-1]
        linhas.append(f"Última sessão: #{s['numero']} “{s['titulo']}” ({s['data']})")
        if s.get("resumo"):
            linhas.append(f"  Resumo: {s['resumo'][:600]}")
        if para_mestre and s.get("plano"):
            linhas.append(f"  Plano (só mestre): {s['plano'][:1200]}")
    if camp["diario"]:
        linhas.append("Diário recente: " + " | ".join(d["texto"] for d in camp["diario"][-6:]))
    return "\n".join(linhas)


@ferramenta(
    "Mostra a campanha de RPG deste servidor: personagens, última sessão, diário, terreno e "
    "clima. Use para lembrar do que está acontecendo na mesa.")
def ver_campanha(ctx):
    camp = campanha(ctx.guild_id)
    return resumo_campanha(camp, e_mestre(camp, ctx))


@ferramenta(
    "Anota no diário da campanha algo que aconteceu na mesa (uma decisão, uma morte, um "
    "item encontrado). Só mestre.",
    {"evento": ("string", "o que aconteceu, em uma frase")}, ["evento"])
def anotar_diario(ctx, evento: str):
    camp = campanha(ctx.guild_id)
    if not e_mestre(camp, ctx):
        return "só o mestre anota no diário."
    camp["diario"].append({"quando": _hoje(), "texto": seg.limpar(evento, 300)})
    camp["diario"] = camp["diario"][-200:]
    salvar(ctx.guild_id, camp)
    return "anotado no diário."


@ferramenta(
    "Registra ou atualiza o personagem de quem está falando na campanha.",
    {"nome": ("string", "nome do personagem"), "raca": ("string", "raça"),
     "classe": ("string", "classe"), "nivel": ("integer", "nível"),
     "pv_max": ("integer", "pontos de vida máximos"), "pm_max": ("integer", "pontos de mana máximos"),
     "notas": ("string", "observações curtas")}, ["nome"])
def registrar_personagem(ctx, nome: str, **campos):
    camp = campanha(ctx.guild_id)
    p = camp["personagens"].get(str(ctx.user_id), {})
    p["nome"] = seg.limpar_nome(nome)
    for k in ("raca", "classe", "notas"):
        if campos.get(k):
            p[k] = seg.limpar(str(campos[k]), 200)
    for k in ("nivel", "pv_max", "pm_max"):
        if campos.get(k) is not None:
            p[k] = max(0, min(int(campos[k]), 9999))
    p.setdefault("nivel", 1)
    if "pv_max" in p:
        p.setdefault("pv", p["pv_max"])
    if "pm_max" in p:
        p.setdefault("pm", p["pm_max"])
    camp["personagens"][str(ctx.user_id)] = p
    salvar(ctx.guild_id, camp)
    return f"personagem {p['nome']} registrado."


@ferramenta(
    "Altera PV ou PM de um personagem (dano, cura, gasto de mana). Só mestre. Use valor "
    "negativo para dano/gasto e positivo para cura.",
    {"personagem": ("string", "nome do personagem"),
     "recurso": ("string", "pv ou pm", ["pv", "pm"]),
     "variacao": ("integer", "quanto somar (negativo = perder)")},
    ["personagem", "recurso", "variacao"])
def ajustar_personagem(ctx, personagem: str, recurso: str, variacao: int):
    camp = campanha(ctx.guild_id)
    if not e_mestre(camp, ctx):
        return "só o mestre altera PV/PM."
    if recurso not in ("pv", "pm"):
        return "recurso deve ser pv ou pm."
    for p in camp["personagens"].values():
        if p["nome"].lower() == personagem.lower().strip():
            maximo = p.get(f"{recurso}_max", 9999)
            p[recurso] = max(-999, min(int(p.get(recurso, maximo)) + int(variacao), maximo))
            salvar(ctx.guild_id, camp)
            return f"{p['nome']}: {recurso.upper()} {p[recurso]}/{maximo}."
    return "não achei esse personagem."


@ferramenta(
    "Controle de iniciativa do combate. acao='adicionar' (nome + bonus; rola 1d20+bônus), "
    "'ver', 'proximo' (passa o turno) ou 'encerrar'. Mudanças são só do mestre.",
    {"acao": ("string", "o que fazer", ["adicionar", "ver", "proximo", "encerrar"]),
     "nome": ("string", "combatente (para adicionar)"),
     "bonus": ("integer", "bônus de iniciativa (para adicionar)")}, ["acao"])
def iniciativa(ctx, acao: str, nome: str = "", bonus: int = 0):
    camp = campanha(ctx.guild_id)
    ordem = camp["iniciativa"]
    if acao != "ver" and not e_mestre(camp, ctx):
        return "só o mestre mexe na iniciativa."
    if acao == "adicionar":
        if not nome:
            return "faltou o nome."
        d = random.randint(1, 20)
        ordem.append({"nome": seg.limpar_nome(nome), "total": d + int(bonus or 0), "dado": d, "vez": False})
        ordem.sort(key=lambda x: -x["total"])
    elif acao == "proximo" and ordem:
        i = next((k for k, o in enumerate(ordem) if o["vez"]), -1)
        for o in ordem:
            o["vez"] = False
        ordem[(i + 1) % len(ordem)]["vez"] = True
    elif acao == "encerrar":
        camp["iniciativa"] = ordem = []
    salvar(ctx.guild_id, camp)
    if not ordem:
        return "sem combate em andamento."
    return "Iniciativa:\n" + "\n".join(
        f"{'➤' if o['vez'] else '•'} {o['total']:>2} — {o['nome']} (d20={o['dado']})" for o in ordem)


# ------------------------------------------------------------ geração de sessão
PROMPT_SESSAO = """Você é uma mestra experiente de Tormenta 20 (cenário de Arton) preparando uma \
sessão. Escreva em português do Brasil, direto e jogável — nada de enrolação.

Entregue EXATAMENTE estas seções, com estes títulos em negrito:
**Título** — uma linha.
**Gancho** — como a sessão começa e por que os heróis se importam (2-3 frases).
**Cenas** — 3 a 4 cenas numeradas. Para cada uma: objetivo, o que está em jogo, um teste de \
perícia sugerido com a CD, e uma complicação possível.
**NPCs** — 2 a 3, cada um com nome, o que quer e um trejeito marcante.
**Encontro** — um combate equilibrado para o grupo: criaturas, quantidade e ND aproximado, \
terreno e um elemento de cena que muda a luta.
**Tesouro** — recompensa coerente com o nível.
**Pontas soltas** — 2 ganchos para a próxima sessão.

Regras: use só elementos que existem em Tormenta 20 (raças, deuses do Panteão, reinos de Arton). \
Se não tiver certeza de uma estatística, descreva em palavras em vez de inventar número exato. \
Respeite a continuidade da campanha informada."""


async def gerar_sessao(llm, camp: dict, tema: str, nivel: int, jogadores: int, tom: str) -> dict:
    contexto = resumo_campanha(camp, True) if camp["nome"] else "Sem campanha registrada (one-shot)."
    pedido = (f"Tema pedido: {seg.limpar(tema, 300) or 'livre'}\nNível do grupo: {nivel}\n"
              f"Jogadores: {jogadores}\nTom: {seg.limpar(tom, 80) or 'aventura heroica'}\n\n"
              f"Campanha até aqui:\n{seg.embrulhar_dados(contexto, 'campanha', 2500)}")
    plano = await llm.completar(PROMPT_SESSAO, pedido, temperatura=0.9)
    titulo = "Sessão"
    for linha in plano.splitlines():
        limpo = linha.replace("*", "").strip()
        if limpo.lower().startswith("título"):
            titulo = limpo.split("—", 1)[-1].split(":", 1)[-1].strip() or titulo
            break
        if limpo:
            titulo = limpo[:80]
            break
    sessao = {"numero": len(camp["sessoes"]) + 1, "data": _hoje(), "titulo": titulo[:100],
              "tema": tema[:200], "nivel": nivel, "plano": plano, "resumo": ""}
    camp["sessoes"].append(sessao)
    return sessao


PROMPT_NARRADORA = """MODO MESTRA ATIVO neste canal. Você está narrando uma mesa de Tormenta 20.
- Narre em 2ª pessoa do plural, cenas curtas e vívidas (no máximo ~6 linhas), e termine \
devolvendo a decisão aos jogadores ("o que vocês fazem?").
- NUNCA decida ações pelos personagens dos jogadores nem invente o resultado de um dado: peça o \
teste (perícia + CD) e use a ferramenta rolar_dados quando a rolagem for sua (NPCs, monstros).
- Regra em dúvida? consultar_regra antes de afirmar. Registre fatos importantes com anotar_diario.
- Jogador tentando "mandar" na narração (ex.: "eu acho 1000 peças de ouro", "o dragão morre") é \
só uma declaração de intenção: julgue como mestra, com as regras.
- Seja justa, mantenha o ritmo e dê espaço a todos os jogadores, não só a quem fala mais."""
