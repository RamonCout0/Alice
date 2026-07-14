# ============================================================
#  frontends/cli.py — Alice no terminal (agente de código)
#
#  Rodar (de dentro da pasta Alice 2.0):
#      python -m frontends.cli
#      python -m frontends.cli /caminho/do/projeto
# ============================================================
import os
import sys

# permite `python frontends/cli.py` além de `python -m frontends.cli`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config, build_system_prompt
from core.agent import Agent
from core import tools, memory
from mcp_bridge.bridge import carregar_mcp

# cores ANSI
DIM, CYAN, YEL, GRN, RST = "\033[2m", "\033[36m", "\033[33m", "\033[32m", "\033[0m"


def confirmar_comando(cmd: str) -> bool:
    resp = input(f"\n  {YEL}⚠ rodar comando?{RST} {cmd}\n  [s/N] ")
    return resp.strip().lower() in {"s", "sim", "y", "yes"}


def banner(cfg):
    print(f"{CYAN}╭─────────────────────────────────────────────╮{RST}")
    print(f"{CYAN}│{RST}  🤖 Alice 2.0 — assistente de código        {CYAN}│{RST}")
    print(f"{CYAN}│{RST}  modelo: {cfg.model:<34}{CYAN}│{RST}")
    print(f"{CYAN}│{RST}  projeto: {os.path.abspath(cfg.workdir)[:33]:<33}{CYAN}│{RST}")
    print(f"{CYAN}╰─────────────────────────────────────────────╯{RST}")
    print(f"{DIM}comandos: /reset  /cwd <pasta>  /salvar <nome>  /sair{RST}\n")


def main():
    cfg = load_config()
    if len(sys.argv) > 1:
        cfg.workdir = sys.argv[1]

    tools.configure(
        workdir=cfg.workdir,
        confirm_cb=confirmar_comando if cfg.confirm_commands else None,
        godot_bin=cfg.godot_bin,
    )
    extra_tools, extra_dispatch = carregar_mcp(cfg)
    alice = Agent(cfg, build_system_prompt(cfg), extra_tools, extra_dispatch)

    banner(cfg)

    while True:
        try:
            user = input(f"{GRN}você ›{RST} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\naté mais! 👋")
            break

        if not user:
            continue
        if user in {"/sair", "/exit", "sair"}:
            print("até mais! 👋")
            break
        if user == "/reset":
            alice.reset()
            print(f"{DIM}histórico limpo.{RST}\n")
            continue
        if user.startswith("/cwd "):
            novo = user[5:].strip()
            cfg.workdir = novo
            tools.configure(workdir=novo, confirm_cb=confirmar_comando if cfg.confirm_commands else None, godot_bin=cfg.godot_bin)
            print(f"{DIM}projeto agora: {os.path.abspath(novo)}{RST}\n")
            continue
        if user.startswith("/salvar "):
            memory.salvar(user[8:].strip(), alice.messages)
            print(f"{DIM}sessão salva.{RST}\n")
            continue

        print(f"{CYAN}alice ›{RST} ", end="", flush=True)
        for kind, dado in alice.stream(user):
            if kind == "text":
                print(dado, end="", flush=True)
            elif kind == "tool":
                nome, args = dado
                resumo = ", ".join(f"{k}={str(v)[:40]}" for k, v in (args or {}).items())
                print(f"\n{DIM}  ⚙ {nome}({resumo}){RST}\n  ", end="", flush=True)
        print("\n")


if __name__ == "__main__":
    main()
