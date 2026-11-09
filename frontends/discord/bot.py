# ============================================================
#  frontends/discord/bot.py — Alice (NAVI GM, a "segunda IRIS") no Discord
#
#  • Em canais: UM Agent por canal — ela acompanha o papo do grupo; cada fala
#    chega marcada com [Nome] pra ela saber quem é quem.
#  • Em DM: um Agent por pessoa. Só na DM com o dono entra o perfil pessoal dele
#    (num canal compartilhado isso vazaria pra todo mundo).
#  • Memória por pessoa (apelido, poucos fatos, sumiço) em core/pessoas.py.
#  • Só uma ferramenta: pesquisar_web (DuckDuckGo). Não toca no disco.
#
#  Mencione @Alice, responda a ela, ou cite o nome dela.
#
#  Rodar (de dentro da pasta Alice 2.0):
#      python -m frontends.discord.bot
# ============================================================
import os
import re
import sys
import asyncio
import dataclasses
from collections import deque

# ela responde se marcada OU se chamarem o nome dela na mensagem
_NOME_RX = re.compile(r"\balice\b", re.IGNORECASE)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import discord
from discord.ext import commands

from core.config import load_config, build_system_prompt
from core.agent import Agent
from core import tools, navi, pessoas

cfg = load_config()
tools.configure(workdir=cfg.workdir, confirm_cb=None, godot_bin=cfg.godot_bin)

# Prompt público (canais) x prompt do dono (só na DM com ele): o segundo inclui o
# perfil pessoal e a memória de longo prazo do Ramon.
SYSTEM_PUBLICO = build_system_prompt(cfg, modo="gm")
SYSTEM_DONO = build_system_prompt(cfg, modo="gm_dono")

# SEGURANÇA: qualquer um no Discord pode falar com ela; ninguém — nem o dono —
# cria/edita/roda nada por aqui. A ÚNICA ferramenta liberada é a pesquisa na web
# (DuckDuckGo), somente leitura e com limite de frequência.
_PERMITIDAS = {"pesquisar_web"}
_SEM_FERRAMENTAS = {fn.__name__ for fn in tools.LOCAL_TOOLS} - _PERMITIDAS
# poucas rodadas: pesquisa uma vez, responde. Evita loop de ferramenta num 8B.
cfg_discord = dataclasses.replace(cfg, max_tool_rounds=3)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

_agentes: dict[str, Agent] = {}                 # "c<canal>" ou "d<usuario>"
_recentes: dict[int, deque] = {}                # últimas falas do canal que NÃO eram pra ela
_falas: dict[int, list[str]] = {}               # falas recentes dela com cada pessoa (p/ aprender)

# só uma geração por vez no Ollama — evita várias pessoas falando juntas travarem o PC
_FILA_GPU = asyncio.Semaphore(1)


def _eh_dm(message) -> bool:
    return message.guild is None


def agente_de(message: discord.Message) -> Agent:
    if _eh_dm(message):
        chave = f"d{message.author.id}"
        system = SYSTEM_DONO if message.author.id == cfg.owner_discord_id else SYSTEM_PUBLICO
    else:
        chave = f"c{message.channel.id}"
        system = SYSTEM_PUBLICO
    if chave not in _agentes:
        _agentes[chave] = Agent(cfg_discord, system, exclude_tools=_SEM_FERRAMENTAS)
    return _agentes[chave]


@bot.event
async def on_ready():
    print(f"Alice 2.0 online → {bot.user}  | modelo: {cfg.model}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="a NAVICity"))


async def _aprender(uid: int, agente: Agent):
    """Em segundo plano, depois de responder: tenta guardar até 2 fatos novos."""
    falas = list(_falas.get(uid, []))
    if not falas:
        return
    loop = asyncio.get_event_loop()
    async with _FILA_GPU:
        fatos = await loop.run_in_executor(
            None, pessoas.extrair_fatos, agente.client, cfg.model, falas, cfg.keep_alive)
    if fatos:
        pessoas.adicionar_fatos(uid, fatos)
    _falas[uid] = []


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    if message.content.startswith("!"):
        return

    # responde se: for marcada (@Alice), for resposta a ela, citarem o nome, ou for DM
    mencionada = bot.user in message.mentions
    respondendo = bool(message.reference) and getattr(message.reference.resolved, "author", None) == bot.user
    pelo_nome = bool(_NOME_RX.search(message.content))
    if not (mencionada or respondendo or pelo_nome or _eh_dm(message)):
        # papo que não é pra ela: guarda um resumo curto só pra ela entender o clima depois
        if not _eh_dm(message) and message.content.strip():
            buf = _recentes.setdefault(message.channel.id, deque(maxlen=4))
            buf.append(f"[{message.author.display_name}] {message.content.strip()[:120]}")
        return

    pergunta = message.content.replace(f"<@{bot.user.id}>", "").strip()
    if len(pergunta) < 2:
        await message.reply("oi, pode falar. Tô por aqui.")
        return

    uid = message.author.id
    p = pessoas.registrar_contato(uid, message.author.display_name)
    nome = pessoas.nome_para(p)

    partes = []
    ctx_pessoa = pessoas.contexto(p)
    if ctx_pessoa:
        partes.append(ctx_pessoa)
    buf = _recentes.pop(message.channel.id, None)
    if buf:
        partes.append("(no canal, antes: " + " | ".join(buf) + ")")
    # anexa só os trechos do Códice que a pergunta pede (contexto leve p/ o 8B)
    partes.append(navi.com_contexto(f"[{nome}] {pergunta}"))
    entrada = "\n".join(partes)

    alice = agente_de(message)
    async with message.channel.typing():
        loop = asyncio.get_event_loop()
        # fila serial: só UMA geração por vez na GPU, o resto espera sua vez.
        # (send() é bloqueante -> roda fora do event loop)
        async with _FILA_GPU:
            resposta = await loop.run_in_executor(None, alice.send, entrada)

    # Discord limita mensagens a 2000 chars
    for i in range(0, len(resposta), 1900):
        parte = resposta[i:i + 1900]
        await (message.reply(parte) if i == 0 else message.channel.send(parte))

    # convivência: a cada N falas dela com a pessoa, tenta aprender algo sobre ela
    falas = _falas.setdefault(uid, [])
    falas.append(pergunta[:200])
    if p["msgs"] % pessoas.APRENDER_A_CADA == 0:
        asyncio.create_task(_aprender(uid, alice))


# ------------------------------------------------------------------ comandos
@bot.command(name="apelido")
async def apelido(ctx, *, nome: str = ""):
    """!apelido Fulano — como ela deve te chamar."""
    if not nome.strip():
        await ctx.send("me diz o apelido: `!apelido Fulano`")
        return
    if pessoas.ver(ctx.author.id) is None:
        pessoas.registrar_contato(ctx.author.id, ctx.author.display_name)
    pessoas.definir_apelido(ctx.author.id, nome)
    await ctx.send(f"fechado, {nome.strip()[:30]}.")


@bot.command(name="quem")
async def quem(ctx):
    """!quem — te manda por DM o que ela sabe sobre você (nunca no canal)."""
    p = pessoas.ver(ctx.author.id)
    if not p:
        txt = "ainda não sei nada de você."
    else:
        fatos = "\n".join(f"• {f}" for f in p["fatos"]) or "• (nenhum fato guardado)"
        txt = (f"Isso é o que eu guardo de você:\nNome: {p['nome']}\n"
               f"Apelido: {p['apelido'] or '—'}\nFatos:\n{fatos}\n\n"
               "`!esquecer` apaga tudo isso.")
    try:
        await ctx.author.send(txt)
        if ctx.guild:
            await ctx.send("te mandei por DM.")
    except discord.Forbidden:
        await ctx.send("não consegui te chamar na DM — libera DMs deste servidor e tenta de novo.")


@bot.command(name="esquecer")
async def esquecer(ctx):
    """!esquecer — apaga tudo que ela guardou de você."""
    _falas.pop(ctx.author.id, None)
    await ctx.send("apagado." if pessoas.esquecer(ctx.author.id) else "não tinha nada de você aqui.")


@bot.command(name="reset")
async def reset(ctx):
    """!reset — (só o dono) limpa a conversa deste canal/DM."""
    if ctx.author.id != cfg.owner_discord_id:
        return
    _agentes.pop(f"d{ctx.author.id}" if ctx.guild is None else f"c{ctx.channel.id}", None)
    _recentes.pop(ctx.channel.id, None)
    await ctx.send("conversa daqui zerada.")


if __name__ == "__main__":
    if not cfg.discord_token:
        raise SystemExit("Defina 'discord_token' em config/config.json")
    bot.run(cfg.discord_token)
