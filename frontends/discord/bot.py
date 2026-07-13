# ============================================================
#  frontends/discord/bot.py — Alice no Discord usando o MESMO core
#
#  Cada usuário tem seu próprio Agent (histórico individual).
#  Mencione @Alice para conversar.
#
#  Rodar (de dentro da pasta Alice 2.0):
#      python -m frontends.discord.bot
#
#  Obs: aqui o bot + Ollama rodam no mesmo PC. Se quiser o bot 24/7 na
#  nuvem com inferência no seu PC, a arquitetura Redis da Alice 1.6
#  continua válida — bastaria trocar a camada de transporte.
# ============================================================
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import discord
from discord.ext import commands

from core.config import load_config, build_system_prompt
from core.agent import Agent
from core import tools

cfg = load_config()
# no Discord as ferramentas são globais; comandos rodam sem confirmação interativa.
# MCP (filesystem/git) fica só na CLI de propósito — aqui as ferramentas locais já
# bastam, e run_command é restrito ao owner (ver agente_de) por não ter confirmação.
tools.configure(workdir=cfg.workdir, confirm_cb=None)
SYSTEM = build_system_prompt(cfg)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# um agente por usuário
_agentes: dict[int, Agent] = {}


def agente_de(user_id: int) -> Agent:
    if user_id not in _agentes:
        # run_command não pede confirmação no Discord -> só o owner pode usar
        excluir = set() if user_id == cfg.owner_discord_id else {"run_command"}
        _agentes[user_id] = Agent(cfg, SYSTEM, exclude_tools=excluir)
    return _agentes[user_id]


@bot.event
async def on_ready():
    print(f"Alice 2.0 online → {bot.user}  | modelo: {cfg.model}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="@Alice pra codar!"))


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    if bot.user not in message.mentions:
        return

    pergunta = message.content.replace(f"<@{bot.user.id}>", "").strip()
    if len(pergunta) < 2:
        await message.reply("oi! manda a dúvida de código que eu te ajudo 😊")
        return

    alice = agente_de(message.author.id)
    async with message.channel.typing():
        loop = asyncio.get_event_loop()
        # send() é bloqueante (Ollama) -> roda fora do event loop
        resposta = await loop.run_in_executor(None, alice.send, pergunta)

    # Discord limita mensagens a 2000 chars
    for i in range(0, len(resposta), 1900):
        parte = resposta[i:i + 1900]
        await (message.reply(parte) if i == 0 else message.channel.send(parte))


@bot.command(name="reset")
async def reset(ctx):
    _agentes.pop(ctx.author.id, None)
    await ctx.send("🔄 histórico limpo!")


if __name__ == "__main__":
    if not cfg.discord_token:
        raise SystemExit("Defina 'discord_token' em config/config.json")
    bot.run(cfg.discord_token)
