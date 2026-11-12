"""Cliente do Ollama + loop de ferramentas (assíncrono, via HTTP puro)."""
from __future__ import annotations

import json
import re

import httpx

from alice import ferramentas as fer

_TAG_RX = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_FENCE_RX = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_THINK_RX = re.compile(r"<think>.*?</think>", re.DOTALL)
_DEC = json.JSONDecoder()


def _jsons_soltos(texto: str) -> list:
    achados, i = [], 0
    while i < len(texto):
        if texto[i] == "{":
            try:
                obj, fim = _DEC.raw_decode(texto, i)
                achados.append(obj)
                i = fim
                continue
            except json.JSONDecodeError:
                pass
        i += 1
    return achados


def extrair_chamadas(conteudo: str, validos: set[str]) -> list[dict]:
    """Modelos pequenos às vezes devolvem a chamada como JSON solto no texto."""
    if not conteudo:
        return []
    brutos = _TAG_RX.findall(conteudo) or _FENCE_RX.findall(conteudo)
    objetos = []
    if brutos:
        for b in brutos:
            try:
                objetos.append(json.loads(b))
            except json.JSONDecodeError:
                pass
    else:
        objetos = _jsons_soltos(conteudo)
    saida = []
    for o in objetos:
        if isinstance(o, dict) and o.get("name") in validos:
            args = o.get("arguments") or o.get("parameters") or {}
            saida.append({"function": {"name": o["name"],
                                       "arguments": args if isinstance(args, dict) else {}}})
    return saida


class LLM:
    def __init__(self, cfg):
        self.cfg = cfg
        self.http = httpx.AsyncClient(base_url=cfg.ollama_host, timeout=httpx.Timeout(300, connect=5))
        self._tamanho_b: float | None = None

    async def fechar(self):
        await self.http.aclose()

    async def tamanho_b(self) -> float:
        """Bilhões de parâmetros do modelo (0 se não deu pra descobrir)."""
        if self._tamanho_b is None:
            self._tamanho_b = 0.0
            try:
                r = await self.http.post("/api/show", json={"model": self.cfg.modelo})
                tam = r.json().get("details", {}).get("parameter_size", "")
                m = re.match(r"([\d.]+)\s*([BM])", tam.upper())
                if m:
                    self._tamanho_b = float(m.group(1)) / (1000 if m.group(2) == "M" else 1)
            except (httpx.HTTPError, ValueError):
                pass
            if not self._tamanho_b:
                m = re.search(r"(\d+(?:\.\d+)?)b\b", self.cfg.modelo.lower())
                self._tamanho_b = float(m.group(1)) if m else 0.0
        return self._tamanho_b

    async def pequeno(self) -> bool:
        t = await self.tamanho_b()
        return t == 0 or t <= self.cfg.pequeno_ate_b

    async def _chat(self, mensagens: list, tools: list | None = None,
                    temperatura: float | None = None, formato=None) -> dict:
        corpo = {"model": self.cfg.modelo, "messages": mensagens, "stream": False, "think": False,
                 "options": {"temperature": self.cfg.temperatura if temperatura is None else temperatura,
                             "num_ctx": self.cfg.num_ctx}}
        if tools:
            corpo["tools"] = tools
        if formato:
            corpo["format"] = formato
        r = await self.http.post("/api/chat", json=corpo)
        if r.status_code == 400 and "think" in r.text:      # modelo sem modo "thinking"
            corpo.pop("think")
            r = await self.http.post("/api/chat", json=corpo)
        if r.status_code == 400 and tools and "tools" in r.text:   # modelo sem tool-calling
            corpo.pop("tools")
            r = await self.http.post("/api/chat", json=corpo)
        r.raise_for_status()
        return r.json()["message"]

    async def completar(self, sistema: str, pedido: str, temperatura: float | None = None,
                        formato=None) -> str:
        """Uma chamada simples, sem ferramentas (resumos, geração de sessão…)."""
        m = await self._chat([{"role": "system", "content": sistema},
                              {"role": "user", "content": pedido}],
                             temperatura=temperatura, formato=formato)
        return _THINK_RX.sub("", m.get("content") or "").strip()

    async def conversar(self, mensagens: list, ctx: fer.Contexto, usar_ferramentas: bool = True,
                        ao_usar=None) -> str:
        """Roda o loop até sair texto. `mensagens` é modificada no lugar."""
        specs = fer.specs_para(ctx.nivel) if usar_ferramentas else []
        validos = {s["function"]["name"] for s in specs}
        vistos: set[str] = set()
        for _ in range(self.cfg.max_rodadas_ferramenta):
            m = await self._chat(mensagens, specs)
            conteudo = _THINK_RX.sub("", m.get("content") or "").strip()
            chamadas = m.get("tool_calls") or extrair_chamadas(conteudo, validos)
            if not chamadas:
                if conteudo:
                    return conteudo
                mensagens.append({"role": "user", "content": "(sua resposta saiu vazia — responda agora.)"})
                continue
            mensagens.append({"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": c["function"]["name"],
                              "arguments": c["function"].get("arguments") or {}}} for c in chamadas]})
            for c in chamadas:
                nome = c["function"]["name"]
                args = c["function"].get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                chave = nome + json.dumps(args, sort_keys=True, ensure_ascii=False)
                if chave in vistos:
                    resultado = "Você já fez essa mesma chamada. Use o resultado anterior e responda."
                else:
                    vistos.add(chave)
                    if ao_usar:
                        await ao_usar(nome, args)
                    resultado = await fer.executar(nome, args, ctx)
                mensagens.append({"role": "tool", "tool_name": nome, "content": resultado})
        # estourou as rodadas: força uma resposta final sem ferramentas
        mensagens.append({"role": "user", "content": "(chega de ferramentas — responda com o que já tem.)"})
        m = await self._chat(mensagens)
        return _THINK_RX.sub("", m.get("content") or "").strip() or "travei aqui, tenta de novo?"
