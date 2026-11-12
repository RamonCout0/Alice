"""Geração de imagem local via ComfyUI (SDXL) — pensado para uma RTX 5060 Ti.

Por que ComfyUI + SDXL: tem API HTTP estável, o SDXL roda folgado em 16 GB
(e cabe em 8 GB), e os checkpoints da família Illustrious/Juggernaut entregam
imagem bonita em ~25 passos. O workflow é montado aqui em código, então não
precisa exportar nada da interface.

Com `liberar_vram`, o modelo de texto é descarregado do Ollama antes de gerar
e o ComfyUI libera a VRAM depois — os dois não brigam pela mesma placa.
"""
from __future__ import annotations

import asyncio
import random
import re
import uuid

import httpx

from alice import seguranca as seg
from alice.ferramentas import ferramenta

ESTILOS = {
    "anime": {
        "positivo": "masterpiece, best quality, amazing quality, absurdres, {p}, detailed "
                    "background, beautiful lighting, vibrant colors",
        "negativo": "bad quality, worst quality, lowres, bad anatomy, bad hands, extra digits, "
                    "jpeg artifacts, signature, watermark, text, nsfw, nude",
        "passos": 26, "cfg": 5.5, "sampler": "euler_ancestral", "scheduler": "normal",
    },
    "realista": {
        "positivo": "{p}, highly detailed, cinematic lighting, sharp focus, 35mm photograph, "
                    "natural colors",
        "negativo": "cartoon, 3d render, lowres, blurry, deformed, bad anatomy, watermark, text, "
                    "nsfw, nude",
        "passos": 28, "cfg": 4.5, "sampler": "dpmpp_2m_sde", "scheduler": "karras",
    },
    "pixel": {
        "positivo": "pixel art, {p}, simple flat colors, clean outline, limited palette, "
                    "game sprite, centered, plain background",
        "negativo": "blurry, gradient, 3d, photo, realistic, noisy, jpeg artifacts, text, "
                    "watermark, nsfw, nude",
        "passos": 24, "cfg": 6.0, "sampler": "euler_ancestral", "scheduler": "normal",
    },
}
FORMATOS = {"quadrado": (1024, 1024), "retrato": (832, 1216), "paisagem": (1216, 832)}

# Bloqueio simples de conteúdo: o bot fica num servidor com várias pessoas.
_PROIBIDO = re.compile(
    r"(?i)\b(nsfw|nude|naked|nua?s?\b|pelad[ao]s?|sexo|sexual|porn\w*|hentai|genit\w+|"
    r"loli\w*|shota\w*|crian[çc]a.{0,20}(sensual|sexy)|gore|desmembr\w+)")


class ImagemIndisponivel(Exception):
    pass


def montar_workflow(checkpoint: str, positivo: str, negativo: str, largura: int, altura: int,
                    passos: int, cfg: float, sampler: str, scheduler: str, semente: int,
                    lora: str = "", forca_lora: float = 0.9) -> dict:
    wf = {
        "ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": positivo, "clip": ["ckpt", 1]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": negativo, "clip": ["ckpt", 1]}},
        "lat": {"class_type": "EmptyLatentImage",
                "inputs": {"width": largura, "height": altura, "batch_size": 1}},
        "ks": {"class_type": "KSampler", "inputs": {
            "model": ["ckpt", 0], "positive": ["pos", 0], "negative": ["neg", 0],
            "latent_image": ["lat", 0], "seed": semente, "steps": passos, "cfg": cfg,
            "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0}},
        "vae": {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["ckpt", 2]}},
        "save": {"class_type": "SaveImage", "inputs": {"images": ["vae", 0], "filename_prefix": "alice"}},
    }
    if lora:
        wf["lora"] = {"class_type": "LoraLoader", "inputs": {
            "lora_name": lora, "strength_model": forca_lora, "strength_clip": forca_lora,
            "model": ["ckpt", 0], "clip": ["ckpt", 1]}}
        wf["ks"]["inputs"]["model"] = ["lora", 0]
        wf["pos"]["inputs"]["clip"] = ["lora", 1]
        wf["neg"]["inputs"]["clip"] = ["lora", 1]
    return wf


async def _descarregar_llm(cfg) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{cfg.ollama_host}/api/generate", json={"model": cfg.modelo, "keep_alive": 0})
    except httpx.HTTPError:
        pass


async def gerar(cfg, prompt: str, estilo: str = "anime", formato: str = "quadrado",
                semente: int | None = None, **ajustes) -> tuple[bytes, dict]:
    """Devolve (png, parâmetros usados). Levanta ImagemIndisponivel se o ComfyUI não responder."""
    est = {**ESTILOS.get(estilo, ESTILOS["anime"]), **{k: v for k, v in ajustes.items() if v is not None}}
    largura, altura = FORMATOS.get(formato, FORMATOS["quadrado"])
    semente = semente if semente is not None else random.randint(0, 2**31 - 1)
    usados = {"estilo": estilo, "formato": formato, "semente": semente, "passos": est["passos"],
              "cfg": est["cfg"], "sampler": est["sampler"]}
    wf = montar_workflow(
        cfg.comfy_modelos.get(estilo, cfg.comfy_modelos["anime"]),
        est["positivo"].format(p=prompt), est["negativo"], largura, altura,
        int(est["passos"]), float(est["cfg"]), est["sampler"], est["scheduler"], semente,
        lora=cfg.comfy_lora_pixel if estilo == "pixel" else "")
    if cfg.liberar_vram:
        await _descarregar_llm(cfg)
    base = cfg.comfy_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{base}/prompt", json={"prompt": wf, "client_id": uuid.uuid4().hex})
            if r.status_code != 200:
                raise ImagemIndisponivel(f"ComfyUI recusou o workflow: {r.text[:300]}")
            pid = r.json()["prompt_id"]
            for _ in range(240):                       # até ~4 min
                await asyncio.sleep(1)
                h = (await c.get(f"{base}/history/{pid}")).json().get(pid)
                if not h:
                    continue
                if h.get("status", {}).get("status_str") == "error":
                    raise ImagemIndisponivel("o ComfyUI deu erro ao gerar (confira o checkpoint/LoRA).")
                for saida in h.get("outputs", {}).values():
                    for img in saida.get("images", []):
                        dados = await c.get(f"{base}/view", params={
                            "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output")})
                        if cfg.liberar_vram:
                            await c.post(f"{base}/free", json={"unload_models": True, "free_memory": True})
                        return dados.content, usados
            raise ImagemIndisponivel("a geração demorou demais.")
    except httpx.HTTPError as e:
        raise ImagemIndisponivel(f"não consegui falar com o ComfyUI em {base} ({type(e).__name__}). "
                                 "Ele está aberto?") from e


def prompt_permitido(prompt: str) -> bool:
    return not _PROIBIDO.search(prompt or "")


_limite = None


@ferramenta(
    "Gera uma imagem (ilustração) a partir de uma descrição. Escreva o prompt em INGLÊS, com "
    "tags separadas por vírgula descrevendo sujeito, roupa, cenário, luz e clima. A imagem é "
    "anexada sozinha à sua resposta.",
    {"prompt": ("string", "descrição em inglês, estilo tags"),
     "estilo": ("string", "estilo visual", ["anime", "realista"]),
     "formato": ("string", "proporção", ["quadrado", "retrato", "paisagem"])}, ["prompt"])
async def gerar_imagem(ctx, prompt: str, estilo: str = "anime", formato: str = "quadrado"):
    global _limite
    if not prompt_permitido(prompt):
        return "esse pedido eu não desenho (conteúdo adulto/violento explícito). Ofereça outra ideia."
    if _limite is None:
        _limite = seg.LimitePorHora(ctx.cfg.imagens_por_hora)
    if ctx.nivel < seg.CONFIAVEL and not _limite.consumir(ctx.user_id):
        return "a pessoa já gerou imagens demais nesta hora; peça pra esperar um pouco."
    if estilo not in ("anime", "realista"):
        estilo = "anime"
    try:
        png, usados = await gerar(ctx.cfg, seg.limpar(prompt, 600), estilo, formato)
    except ImagemIndisponivel as e:
        return f"não deu pra gerar: {e}"
    ctx.arquivos.append((f"alice_{usados['semente']}.png", png))
    return f"imagem gerada e anexada (estilo {estilo}, semente {usados['semente']}). Comente em uma frase."
