"""Argos — o scanner de brechas do Ramon, chamado pela Alice.

Só o DONO usa. O modelo nunca passa um caminho: ele escolhe um APELIDO que
está em `argos_projetos` no config, então não dá pra apontar o scanner (nem
qualquer comando) para uma pasta arbitrária. O processo roda sem shell.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from alice import seguranca as seg
from alice.ferramentas import ferramenta


async def escanear(cfg, apelido: str) -> dict:
    pasta = cfg.argos_projetos.get(apelido)
    if not pasta:
        return {"erro": f"projeto '{apelido}' não está na lista. Disponíveis: "
                        f"{', '.join(cfg.argos_projetos) or 'nenhum'}"}
    cli = Path(cfg.argos_dir) / "cli.py"
    if not cli.is_file() or not Path(pasta).is_dir():
        return {"erro": "argos_dir ou a pasta do projeto não existe (confira o config)."}
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(cli), "scan", str(pasta), "--json",
        cwd=str(cfg.argos_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        saida, erro = await asyncio.wait_for(proc.communicate(), 600)
    except asyncio.TimeoutError:
        proc.kill()
        return {"erro": "o scan passou de 10 minutos e foi cancelado."}
    texto = saida.decode("utf-8", "replace")
    inicio = texto.find("\n{")
    try:
        return json.loads(texto[inicio + 1:] if inicio >= 0 else texto)
    except json.JSONDecodeError:
        return {"erro": "não entendi a saída do Argos.", "bruto": (texto or erro.decode("utf-8", "replace"))[-1500:]}


def resumir(apelido: str, r: dict) -> str:
    if "erro" in r:
        return f"Argos: {r['erro']}\n{r.get('bruto', '')}"
    achados = r.get("findings", [])
    abertos = [f for f in achados if f.get("status", "aberto") == "aberto"]
    linhas = [f"Argos em `{apelido}` — score {r.get('score')}/100 · "
              f"{'✅ ok pra prod' if r.get('aprovado') else '⛔ BLOQUEADO'} · {len(abertos)} aberto(s)"]
    ordem = {"critico": 0, "alto": 1, "medio": 2, "baixo": 3, "info": 4}
    for f in sorted(abertos, key=lambda f: ordem.get(str(f.get("severidade")), 9))[:12]:
        fix = (f.get("fix") or {}).get("descricao", "")
        linhas.append(f"[{str(f.get('severidade', '?')).upper()}] {f.get('id')} {f.get('titulo')} — "
                      f"{f.get('local')}" + (f" → {fix}" if fix else ""))
    if len(abertos) > 12:
        linhas.append(f"… e mais {len(abertos) - 12}.")
    return "\n".join(linhas)


@ferramenta(
    "Roda o Argos (scanner de segurança do Ramon) num projeto dele e devolve score, selo e "
    "brechas abertas. Só o dono pode pedir.",
    {"projeto": ("string", "apelido do projeto, como está configurado")}, ["projeto"],
    nivel=seg.DONO, externa=True)
async def argos_scan(ctx, projeto: str):
    return (resumir(projeto, await escanear(ctx.cfg, projeto.strip()))
            + "\n(Resultado completo acima. Resuma para o dono agora, sem chamar outra ferramenta.)")
