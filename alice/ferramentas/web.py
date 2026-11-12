"""Pesquisa na web via DuckDuckGo — o "conhecimento emprestado" de um modelo pequeno."""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from html import unescape
from urllib.parse import urlparse

import httpx

from alice.ferramentas import ferramenta


def _buscar(consulta: str, n: int) -> list[dict]:
    from ddgs import DDGS
    return list(DDGS().text(consulta, region="br-pt", safesearch="moderate", max_results=n))


@ferramenta(
    "Pesquisa na internet (DuckDuckGo). Use para fatos, notícias, datas, regras ou qualquer "
    "coisa de que você não tenha certeza. Devolve título, link e trecho.",
    {"consulta": ("string", "o que pesquisar, em poucas palavras"),
     "resultados": ("integer", "quantos resultados (1 a 8, padrão 5)")},
    ["consulta"], externa=True)
async def pesquisar_web(ctx, consulta: str, resultados: int = 5):
    n = max(1, min(int(resultados or 5), 8))
    try:
        itens = await asyncio.wait_for(asyncio.to_thread(_buscar, consulta[:200], n), 25)
    except Exception as e:
        return f"a pesquisa falhou ({type(e).__name__}). Responda com o que sabe e avise que não confirmou."
    if not itens:
        return "nenhum resultado."
    return "\n\n".join(f"{i + 1}. {r.get('title', '')}\n   {r.get('href', '')}\n   {r.get('body', '')}"
                       for i, r in enumerate(itens))


def _host_publico(host: str) -> bool:
    """Bloqueia SSRF: nada de localhost, rede interna ou metadados de nuvem."""
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                    or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except (socket.gaierror, ValueError):
        return False


_TAGS_LIXO = re.compile(r"(?is)<(script|style|noscript|svg|nav|footer|header|form)\b.*?</\1>")
_TAG = re.compile(r"(?s)<[^>]+>")


@ferramenta(
    "Abre uma página da web e devolve o texto dela. Use depois de pesquisar_web, quando o "
    "trecho do resultado não bastar.",
    {"url": ("string", "endereço http(s) completo")}, ["url"], externa=True)
async def abrir_pagina(ctx, url: str):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return "url inválida."
    if not await asyncio.to_thread(_host_publico, p.hostname):
        return "esse endereço não é público — não abro."
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
                                     headers={"User-Agent": "Mozilla/5.0 (leitor de texto)"}) as c:
            r = await c.get(url)
            saltos = 0
            while r.is_redirect and saltos < 4:      # cada salto é revalidado contra SSRF
                destino = str(r.next_request.url)
                host = urlparse(destino).hostname or ""
                if not await asyncio.to_thread(_host_publico, host):
                    return "o redirecionamento levava a um endereço não público — parei."
                r = await c.get(destino)
                saltos += 1
    except httpx.HTTPError as e:
        return f"não consegui abrir ({type(e).__name__})."
    if "text" not in r.headers.get("content-type", "") and "json" not in r.headers.get("content-type", ""):
        return "a página não é texto."
    html = r.text[:400_000]
    texto = unescape(_TAG.sub(" ", _TAGS_LIXO.sub(" ", html)))
    return re.sub(r"\s+", " ", texto).strip()[:5000]
