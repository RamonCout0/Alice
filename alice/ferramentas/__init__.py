"""Registro de ferramentas com permissão por nível.

Cada ferramenta declara o nível mínimo de quem pode usá-la. O modelo só RECEBE
as specs que o nível de quem falou permite, e `executar` confere de novo —
mesmo que um jailbreak convença o modelo a "chamar" algo proibido, não roda.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from alice import seguranca as seg


@dataclass
class Contexto:
    cfg: Any
    user_id: int = 0
    user_nome: str = ""
    nivel: int = seg.REGULAR
    guild_id: int = 0
    canal_id: int = 0
    servicos: Any = None                      # LLM, voz etc. (preenchido pelo bot)
    arquivos: list = field(default_factory=list)   # [(nome, bytes)] a anexar na resposta
    anexos_recebidos: list = field(default_factory=list)  # [(nome, bytes)] vindos do usuário


@dataclass
class Ferramenta:
    nome: str
    fn: Callable
    descricao: str
    params: dict
    obrigatorios: list
    nivel: int
    externa: bool          # resultado vem de fora (web/arquivo) → embrulhar como dado


_REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(descricao: str, params: dict | None = None, obrigatorios: list | None = None,
               nivel: int = seg.REGULAR, externa: bool = False):
    """params: {nome: (tipo_json, descrição)} ou {nome: (tipo, descrição, [enum])}."""
    def deco(fn):
        _REGISTRO[fn.__name__] = Ferramenta(fn.__name__, fn, descricao, params or {},
                                            obrigatorios or [], nivel, externa)
        return fn
    return deco


def specs_para(nivel: int) -> list[dict]:
    specs = []
    for f in _REGISTRO.values():
        if nivel < f.nivel:
            continue
        props = {}
        for nome, d in f.params.items():
            props[nome] = {"type": d[0], "description": d[1]}
            if len(d) > 2:
                props[nome]["enum"] = d[2]
        specs.append({"type": "function", "function": {
            "name": f.nome, "description": f.descricao,
            "parameters": {"type": "object", "properties": props, "required": f.obrigatorios}}})
    return specs


async def executar(nome: str, args: dict, ctx: Contexto, limite: int = 6000) -> str:
    f = _REGISTRO.get(nome)
    if f is None:
        return f"ERRO: ferramenta '{nome}' não existe."
    if ctx.nivel < f.nivel:
        return "ERRO: quem pediu não tem permissão para isso. Diga que não pode e siga a conversa."
    aceitos = {k: v for k, v in (args or {}).items() if k in f.params}
    faltando = [o for o in f.obrigatorios if o not in aceitos]
    if faltando:
        return f"ERRO: faltou o parâmetro {', '.join(faltando)}."
    try:
        r = f.fn(ctx, **aceitos)
        if inspect.isawaitable(r):
            r = await r
    except Exception as e:  # ferramenta nunca derruba a conversa
        return f"ERRO em {nome}: {type(e).__name__}: {e}"
    r = str(r)
    return seg.embrulhar_dados(r, nome, limite) if f.externa else r[:limite]


def carregar_todas() -> None:
    """Importa os módulos para que os @ferramenta se registrem."""
    from alice.ferramentas import (web, t20, rpg, imagem, pixelart,  # noqa: F401
                                   gatuno, argos, notas)


def nomes() -> list[str]:
    return sorted(_REGISTRO)
