"""Skill de pixel art que melhora por tentativa e erro.

Como funciona:
  1. BASE    — uma imagem do ComfyUI (estilo "pixel") ou uma imagem enviada.
  2. RECEITA — parâmetros da conversão: tamanho da grade, paleta, contorno,
               limpeza de pixels órfãos, passos/CFG da geração.
  3. NOTA    — cada resultado recebe uma nota automática (métricas abaixo) e,
               depois, a nota humana das reações 👍/👎 no Discord.
  4. APRENDE — cada valor de cada parâmetro é um "braço" com média de
               recompensa (bandit UCB). Na próxima vez ela escolhe mais o que
               deu certo e ainda testa o resto de vez em quando.
  5. LIÇÕES  — crítica em texto (só de dono/confiável) vira lição curta, que
               entra no prompt das próximas gerações.

Tudo fica em dados/pixelart/aprendizado.json — dá pra abrir e ler.
"""
from __future__ import annotations

import io
import math
import random
import time

from PIL import Image

from alice import armazenamento as arm
from alice import seguranca as seg
from alice.config import DADOS
from alice.ferramentas import ferramenta
from alice.ferramentas import imagem

ARQ = DADOS / "pixelart" / "aprendizado.json"

PALETAS = {
    "pico8": ["000000", "1D2B53", "7E2553", "008751", "AB5236", "5F574F", "C2C3C7", "FFF1E8",
              "FF004D", "FFA300", "FFEC27", "00E436", "29ADFF", "83769C", "FF77A8", "FFCCAA"],
    "sweetie16": ["1a1c2c", "5d275d", "b13e53", "ef7d57", "ffcd75", "a7f070", "38b764", "257179",
                  "29366f", "3b5dc9", "41a6f6", "73eff7", "f4f4f4", "94b0c2", "566c86", "333c57"],
    "endesga32": ["be4a2f", "d77643", "ead4aa", "e4a672", "b86f50", "733e39", "3e2731", "a22633",
                  "e43b44", "f77622", "feae34", "fee761", "63c74d", "3e8948", "265c42", "193c3e",
                  "124e89", "0099db", "2ce8f5", "ffffff", "c0cbdc", "8b9bb4", "5a6988", "3a4466",
                  "262b44", "181425", "ff0044", "68386c", "b55088", "f6757a", "e8b796", "c28569"],
    "gameboy": ["0f380f", "306230", "8bac0f", "9bbc0f"],
    "adaptativa16": None,     # paleta tirada da própria imagem (16 cores)
    "adaptativa24": None,
}

# Os "braços": o que ela pode variar entre tentativas.
ESPACO = {
    "grade": [32, 48, 64, 96],
    "paleta": list(PALETAS),
    "contorno": [False, True],
    "limpeza": [0, 1, 2],
    "passos": [20, 24, 30],
    "cfg": [5.0, 6.0, 7.5],
}
PADRAO = {"grade": 64, "paleta": "adaptativa16", "contorno": False, "limpeza": 1, "passos": 24, "cfg": 6.0}


# ------------------------------------------------------------------ conversão
def _paleta_pil(nome: str) -> Image.Image | None:
    hexes = PALETAS.get(nome)
    if not hexes:
        return None
    flat = []
    for h in hexes:
        flat += [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    flat += flat[:3] * (256 - len(hexes))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def pixels(img: Image.Image) -> list[tuple]:
    """Lista de tuplas RGB (substitui o Image.getdata, que sai no Pillow 14)."""
    b = img.convert("RGB").tobytes()
    return [(b[i], b[i + 1], b[i + 2]) for i in range(0, len(b), 3)]


def _limpar_orfaos(img: Image.Image, passadas: int) -> Image.Image:
    """Pixel isolado (nenhum vizinho da mesma cor) vira a cor mais comum ao redor."""
    px = img.load()
    w, h = img.size
    for _ in range(passadas):
        trocas = []
        for y in range(h):
            for x in range(w):
                c = px[x, y]
                viz = [px[x + dx, y + dy] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                       if 0 <= x + dx < w and 0 <= y + dy < h]
                if viz and c not in viz:
                    trocas.append((x, y, max(set(viz), key=viz.count)))
        for x, y, c in trocas:
            px[x, y] = c
        if not trocas:
            break
    return img


def _contornar(img: Image.Image) -> Image.Image:
    """Escurece a borda entre o sujeito e o fundo (fundo = cor do canto)."""
    px = img.load()
    w, h = img.size
    fundo = px[0, 0]
    escura = min(set(pixels(img)), key=lambda c: sum(c[:3]))
    borda = []
    for y in range(h):
        for x in range(w):
            if px[x, y] == fundo:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and px[nx, ny] == fundo:
                    borda.append((x, y))
                    break
    for x, y in borda:
        px[x, y] = escura
    return img


def pixelizar(dados: bytes, receita: dict) -> tuple[bytes, bytes, dict]:
    """Devolve (png ampliado pra ver, png no tamanho real, métricas)."""
    img = Image.open(io.BytesIO(dados)).convert("RGB")
    lado = min(img.size)
    esq, topo = (img.width - lado) // 2, (img.height - lado) // 2
    img = img.crop((esq, topo, esq + lado, topo + lado))
    g = int(receita["grade"])
    pequeno = img.resize((g, g), Image.Resampling.BOX)
    pal = _paleta_pil(receita["paleta"])
    if pal is not None:
        quant = pequeno.quantize(palette=pal, dither=Image.Dither.NONE)
    else:
        n = 24 if receita["paleta"].endswith("24") else 16
        quant = pequeno.quantize(colors=n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    final = quant.convert("RGB")
    if receita.get("limpeza"):
        final = _limpar_orfaos(final, int(receita["limpeza"]))
    if receita.get("contorno"):
        final = _contornar(final)
    metricas = avaliar(final)
    escala = max(1, 512 // g)
    grande = final.resize((g * escala, g * escala), Image.Resampling.NEAREST)
    b1, b2 = io.BytesIO(), io.BytesIO()
    grande.save(b1, "PNG")
    final.save(b2, "PNG")
    return b1.getvalue(), b2.getvalue(), metricas


def avaliar(img: Image.Image) -> dict:
    """Nota automática 0-1: poucas cores, pouco ruído, bom contraste, formas legíveis."""
    px = img.load()
    w, h = img.size
    dados = pixels(img)
    cores = len(set(dados))
    orfaos = iguais = 0
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            viz = [px[x + dx, y + dy] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                   if 0 <= x + dx < w and 0 <= y + dy < h]
            if c not in viz:
                orfaos += 1
            iguais += sum(1 for v in viz if v == c) / len(viz)
    total = w * h
    lum = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in dados]
    media = sum(lum) / total
    contraste = math.sqrt(sum((v - media) ** 2 for v in lum) / total) / 128
    p_orfaos = orfaos / total
    coesao = iguais / total                      # 1 = tudo chapado, 0 = ruído puro
    n_cores = 1.0 if 4 <= cores <= 24 else max(0.0, 1 - abs(cores - 16) / 32)
    n_ruido = max(0.0, 1 - p_orfaos * 12)
    n_forma = 1 - abs(coesao - 0.72) / 0.72      # nem ruído, nem borrão de uma cor só
    n_contraste = min(1.0, contraste / 0.45)
    nota = 0.25 * n_cores + 0.30 * n_ruido + 0.25 * max(0.0, n_forma) + 0.20 * n_contraste
    return {"cores": cores, "orfaos_pct": round(p_orfaos * 100, 2), "coesao": round(coesao, 3),
            "contraste": round(contraste, 3), "nota": round(max(0.0, min(1.0, nota)), 3)}


# ---------------------------------------------------------------- aprendizado
def estado() -> dict:
    return arm.ler(ARQ, lambda: {"bracos": {}, "tentativas": [], "licoes": [], "total": 0})


def _braco(est: dict, param: str, valor) -> dict:
    return est["bracos"].setdefault(param, {}).setdefault(str(valor), {"n": 0, "soma": 0.0})


def escolher_receita(est: dict, explorar: float = 1.0) -> dict:
    """UCB1 por parâmetro: média de recompensa + bônus para o que foi pouco testado."""
    receita = {}
    total = max(1, est["total"])
    for param, valores in ESPACO.items():
        melhor, melhor_ucb = None, -1.0
        for v in valores:
            b = _braco(est, param, v)
            if b["n"] == 0:
                ucb = 1.0 + (0.05 if v == PADRAO[param] else 0) + random.random() * 0.01
            else:
                ucb = b["soma"] / b["n"] + explorar * math.sqrt(2 * math.log(total + 1) / b["n"])
            if ucb > melhor_ucb:
                melhor, melhor_ucb = v, ucb
        receita[param] = melhor
    return receita


def melhor_receita(est: dict) -> dict:
    """A receita que ela considera a melhor até agora (sem explorar)."""
    receita = {}
    for param, valores in ESPACO.items():
        testados = [(b["soma"] / b["n"], v) for v in valores
                    if (b := _braco(est, param, v))["n"] >= 2]
        receita[param] = max(testados, key=lambda t: t[0])[1] if testados else PADRAO[param]
    return receita


def registrar(est: dict, receita: dict, recompensa: float, peso: float = 1.0) -> None:
    for param, valor in receita.items():
        if param in ESPACO:
            b = _braco(est, param, valor)
            b["n"] += peso
            b["soma"] += recompensa * peso
    est["total"] += 1


def nova_tentativa(prompt: str, receita: dict, metricas: dict, autor_id: int) -> str:
    est = estado()
    registrar(est, receita, metricas["nota"], peso=0.5)       # nota automática vale meio voto
    tid = f"px{int(time.time() * 1000) % 10**10}"
    est["tentativas"].append({"id": tid, "prompt": prompt[:200], "receita": receita,
                              "auto": metricas, "votos": {}, "autor": autor_id,
                              "quando": time.strftime("%Y-%m-%d %H:%M")})
    est["tentativas"] = est["tentativas"][-300:]
    arm.gravar(ARQ, est)
    return tid


def votar(tentativa_id: str, user_id: int, gostou: bool) -> bool:
    """Reação 👍/👎. Um voto por pessoa por tentativa; trocar de voto corrige a nota."""
    est = estado()
    t = next((x for x in est["tentativas"] if x["id"] == tentativa_id), None)
    if not t:
        return False
    anterior = t["votos"].get(str(user_id))
    if anterior == gostou:
        return True
    if anterior is not None:                                   # desfaz o voto antigo
        for param, valor in t["receita"].items():
            if param in ESPACO:
                b = _braco(est, param, valor)
                b["n"] = max(0, b["n"] - 1)
                b["soma"] -= 1.0 if anterior else 0.0
    t["votos"][str(user_id)] = gostou
    registrar(est, t["receita"], 1.0 if gostou else 0.0, peso=1.0)
    arm.gravar(ARQ, est)
    return True


def adicionar_licao(texto: str) -> bool:
    texto = seg.limpar(texto, 160)
    if len(texto) < 6 or seg.e_suspeito(texto):
        return False
    est = estado()
    if texto.lower() not in [l["texto"].lower() for l in est["licoes"]]:
        est["licoes"].append({"texto": texto, "quando": time.strftime("%Y-%m-%d")})
        est["licoes"] = est["licoes"][-20:]
        arm.gravar(ARQ, est)
    return True


def relatorio() -> str:
    est = estado()
    if not est["tentativas"]:
        return "Ainda não fiz nenhuma pixel art — sem dados pra aprender."
    linhas = [f"Tentativas: {len(est['tentativas'])} · melhor receita até agora:"]
    for param, valor in melhor_receita(est).items():
        b = _braco(est, param, valor)
        media = f"{b['soma'] / b['n']:.2f}" if b["n"] else "—"
        linhas.append(f"  • {param} = {valor} (média {media}, {b['n']:g} testes)")
    if est["licoes"]:
        linhas.append("Lições: " + " | ".join(l["texto"] for l in est["licoes"][-8:]))
    return "\n".join(linhas)


# ----------------------------------------------------------------- ferramenta
async def criar(ctx, prompt: str, base: bytes | None = None, variantes: int = 3) -> tuple[str, dict]:
    """Gera N variantes com receitas diferentes, fica com a de melhor nota automática."""
    est = estado()
    if base is None:
        dicas = ", ".join(l["texto"] for l in est["licoes"][-5:])
        explorada = escolher_receita(est)
        base, _ = await imagem.gerar(ctx.cfg, prompt + (f", {dicas}" if dicas else ""), "pixel",
                                     passos=explorada["passos"], cfg=explorada["cfg"])
        fixos = {"passos": explorada["passos"], "cfg": explorada["cfg"]}
    else:
        fixos = {"passos": PADRAO["passos"], "cfg": PADRAO["cfg"]}
    candidatas = [melhor_receita(est)] + [escolher_receita(est, 1.5) for _ in range(max(0, variantes - 1))]
    melhor = None
    for receita in candidatas:
        receita = {**receita, **fixos}
        grande, real, metricas = pixelizar(base, receita)
        if melhor is None or metricas["nota"] > melhor[3]["nota"]:
            melhor = (grande, real, receita, metricas)
    grande, real, receita, metricas = melhor
    tid = nova_tentativa(prompt, receita, metricas, ctx.user_id)
    ctx.arquivos.append((f"{tid}.png", grande))
    ctx.arquivos.append((f"{tid}_{receita['grade']}px.png", real))
    return tid, {"receita": receita, "metricas": metricas}


@ferramenta(
    "Cria uma PIXEL ART (sprite, item, personagem, tile). É uma skill sua que aprende com as "
    "reações 👍/👎 das pessoas. Prompt em INGLÊS, curto, um sujeito só. Se a pessoa mandou uma "
    "imagem junto, use converter_anexo=true para transformar a imagem dela em pixel art.",
    {"prompt": ("string", "o que desenhar, em inglês (ex.: 'red potion bottle')"),
     "converter_anexo": ("boolean", "converte a imagem enviada em vez de gerar uma nova")},
    ["prompt"])
async def pixel_art(ctx, prompt: str, converter_anexo: bool = False):
    if not imagem.prompt_permitido(prompt):
        return "esse pedido eu não desenho. Ofereça outra ideia."
    base = None
    if converter_anexo:
        if not ctx.anexos_recebidos:
            return "a pessoa não mandou imagem nenhuma pra converter."
        base = ctx.anexos_recebidos[0][1]
    try:
        tid, info = await criar(ctx, seg.limpar(prompt, 300), base)
    except imagem.ImagemIndisponivel as e:
        return f"não deu pra gerar a base: {e}"
    except OSError:
        return "não consegui ler essa imagem."
    m, r = info["metricas"], info["receita"]
    return (f"pixel art {tid} anexada: grade {r['grade']}px, paleta {r['paleta']}, {m['cores']} cores, "
            f"nota automática {m['nota']}. Peça pra pessoa reagir com 👍 ou 👎 — é assim que você aprende.")
