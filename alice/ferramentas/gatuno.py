"""Gatuno de Estrelas — acompanha a API pública do portal (/api/v1/).

`checar_novidades` é chamado pelo bot a cada N minutos: compara o que a API
devolve com o que já foi visto (dados/gatuno.json) e devolve só o que é novo.
Na primeira execução ele só "decora" o que existe, sem notificar nada.
"""
from __future__ import annotations

import httpx

from alice import armazenamento as arm
from alice import seguranca as seg
from alice.config import DADOS
from alice.ferramentas import ferramenta

ARQ = DADOS / "gatuno.json"

# (rota da API, rótulo, prefixo da página no site, campo de data)
FONTES = {
    "novidades": ("novidades/", "📰 Notícia", "/novidades/", "published_at"),
    "jogos": ("jogos/", "🎮 Jogo", "/jogos/", "release_date"),
    "obras": ("obras/", "📖 Obra", "/obras/", "release_at"),
}


async def _listar(cfg, rota: str) -> list[dict]:
    base = cfg.gatuno_url.rstrip("/")
    async with httpx.AsyncClient(timeout=20, headers={"Accept": "application/json"}) as c:
        r = await c.get(f"{base}/api/v1/{rota}")
        r.raise_for_status()
        dados = r.json()
    return dados.get("results", dados) if isinstance(dados, dict) else dados


def _item(cfg, tipo: str, bruto: dict) -> dict:
    _, rotulo, prefixo, campo_data = FONTES[tipo]
    slug = str(bruto.get("slug", ""))
    autor = bruto.get("author")
    if isinstance(autor, dict):
        autor = autor.get("name") or autor.get("username")
    return {
        "tipo": tipo, "rotulo": rotulo, "slug": slug,
        "titulo": seg.limpar(str(bruto.get("title", "")), 150),
        "resumo": seg.limpar(str(bruto.get("excerpt", "")), 400),
        "autor": seg.limpar_nome(str(autor)) if autor else "",
        "capa": bruto.get("cover") or "",
        "data": str(bruto.get(campo_data) or "")[:10],
        "extra": bruto.get("status_label") or bruto.get("kind_label") or "",
        "capitulos": bruto.get("chapter_count"),
        "url": f"{cfg.gatuno_url.rstrip('/')}{prefixo}{slug}/",
    }


async def catalogo(cfg) -> dict[str, list[dict]]:
    saida = {}
    for tipo, (rota, *_resto) in FONTES.items():
        try:
            saida[tipo] = [_item(cfg, tipo, b) for b in await _listar(cfg, rota)]
        except (httpx.HTTPError, ValueError):
            saida[tipo] = []
    return saida


async def checar_novidades(cfg) -> list[dict]:
    """Itens novos desde a última checagem (inclui obra que ganhou capítulo)."""
    visto = arm.ler(ARQ, dict) or {}
    primeira_vez = not visto
    cat = await catalogo(cfg)
    if not any(cat.values()):
        return []
    novos = []
    for tipo, itens in cat.items():
        vistos_tipo = visto.setdefault(tipo, {})
        for it in itens:
            marca = it["capitulos"] if it["capitulos"] is not None else 1
            antes = vistos_tipo.get(it["slug"])
            if antes is None:
                novos.append(it)
            elif tipo == "obras" and isinstance(antes, int) and marca > antes:
                novos.append({**it, "rotulo": "📖 Capítulo novo",
                              "resumo": f"{it['titulo']} chegou a {marca} capítulos."})
            vistos_tipo[it["slug"]] = marca
    arm.gravar(ARQ, visto)
    return [] if primeira_vez else novos


def formatar(cat: dict[str, list[dict]], por_tipo: int = 6) -> str:
    linhas = []
    for tipo, itens in cat.items():
        if not itens:
            continue
        linhas.append(f"== {tipo} ({len(itens)}) ==")
        for it in itens[:por_tipo]:
            extra = f" [{it['extra']}]" if it["extra"] else ""
            linhas.append(f"- {it['titulo']}{extra} ({it['data']}) — {it['resumo'][:160]} {it['url']}")
    return "\n".join(linhas) or "o site não respondeu agora."


@ferramenta(
    "Consulta o portal Gatuno de Estrelas (estúdio indie do Ramon): notícias, jogos e obras "
    "publicados. Use quando perguntarem novidades do Gatuno ou para dar ideias com base no que "
    "já existe lá.",
    {"tipo": ("string", "filtra por tipo (opcional)", ["novidades", "jogos", "obras"])},
    externa=True)
async def gatuno_novidades(ctx, tipo: str = ""):
    cat = await catalogo(ctx.cfg)
    if tipo in cat:
        cat = {tipo: cat[tipo]}
    return formatar(cat)
