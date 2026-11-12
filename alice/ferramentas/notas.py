"""Ferramentas de memória: o que a Alice guarda sobre quem está falando."""
from __future__ import annotations

from alice import memoria
from alice.ferramentas import ferramenta


@ferramenta(
    "Guarda um fato duradouro sobre a PESSOA QUE ESTÁ FALANDO (gosto, projeto, apelido, "
    "personagem que joga, combinado). Use quando ela contar algo que vale lembrar em conversas "
    "futuras. Uma frase curta, em terceira pessoa.",
    {"fato": ("string", "o fato, ex.: 'joga de paladino de Khalmyr chamado Dorn'")}, ["fato"])
def lembrar(ctx, fato: str):
    ok, motivo = memoria.lembrar(ctx.user_id, fato, ctx.cfg.max_fatos_por_usuario)
    return motivo


@ferramenta(
    "Apaga da sua memória fatos sobre a pessoa que está falando. Com 'trecho', apaga só os "
    "fatos que contêm aquele texto; sem, apaga tudo dela.",
    {"trecho": ("string", "parte do fato a esquecer (opcional)")})
def esquecer(ctx, trecho: str = ""):
    n = memoria.esquecer(ctx.user_id, trecho or None)
    return f"{n} fato(s) apagado(s)."
