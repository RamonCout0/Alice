# ============================================================
#  core/agent.py — o "cérebro": loop de tool-calling com Ollama
#  Frontend-agnóstico: usado pela CLI e pelo bot do Discord.
# ============================================================
import json
import re

import ollama

from core import tools as toolmod
from core.config import Config

_TAG_RX = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_FENCE_RX = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_DECODER = json.JSONDecoder()


def _achar_jsons_soltos(texto: str):
    """Varre o texto procurando objetos JSON completos em qualquer posição,
    mesmo com prosa antes/depois e sem cercas ou tags."""
    achados = []
    i, n = 0, len(texto)
    while i < n:
        if texto[i] == "{":
            try:
                obj, fim = _JSON_DECODER.raw_decode(texto, i)
            except json.JSONDecodeError:
                i += 1
                continue
            achados.append(obj)
            i = fim
        else:
            i += 1
    return achados


def _extract_fallback_tool_calls(content: str):
    """
    Alguns modelos (ex: qwen2.5-coder via Ollama) às vezes devolvem a chamada
    de ferramenta como JSON solto em `content` — puro, em bloco ```json```,
    em <tool_call></tool_call>, ou até misturado com prosa antes sem cerca
    nenhuma — sem preencher `tool_calls`. O parser nativo do Ollama só
    reconhece a forma com tags; aqui cobrimos as outras também.
    """
    if not content:
        return None
    brutos = _TAG_RX.findall(content) or _FENCE_RX.findall(content)
    if brutos:
        objetos = []
        for c in brutos:
            try:
                objetos.append(json.loads(c))
            except (json.JSONDecodeError, TypeError):
                continue
    else:
        objetos = _achar_jsons_soltos(content)

    chamadas = [
        {"function": {"name": data["name"], "arguments": data.get("arguments") or {}}}
        for data in objetos
        if isinstance(data, dict) and "name" in data
    ]
    return chamadas or None


class Agent:
    """
    Um agente conversacional com ferramentas.

    - `extra_tools`   : specs de ferramentas MCP (dicts no formato do Ollama)
    - `extra_dispatch`: mapa {nome_da_ferramenta: callable} para executá-las
    """

    def __init__(self, cfg: Config, system_prompt: str,
                 extra_tools=None, extra_dispatch=None, exclude_tools=None):
        self.cfg = cfg
        self.client = ollama.Client(host=cfg.ollama_host)
        self.messages = [{"role": "system", "content": system_prompt}]

        excluir = exclude_tools or set()
        locais = [fn for fn in toolmod.LOCAL_TOOLS if fn.__name__ not in excluir]

        # dispatch: nome -> função executável
        self.dispatch = {fn.__name__: fn for fn in locais}
        # tools_param: o que é enviado ao modelo (callables locais + specs MCP)
        self.tools_param = list(locais)

        # ferramentas locais têm prioridade: se um servidor MCP expõe uma
        # ferramenta com o mesmo nome (ex: "read_file"), ela é ignorada pra
        # não mandar specs duplicadas/conflitantes pro modelo.
        if extra_tools:
            for spec in extra_tools:
                nome = spec["function"]["name"]
                if nome in self.dispatch:
                    continue
                self.tools_param.append(spec)
        if extra_dispatch:
            for nome, fn in extra_dispatch.items():
                self.dispatch.setdefault(nome, fn)

    # -------------------------------------------------- modo leve
    def _opcoes(self) -> dict:
        op = {"temperature": self.cfg.temperature, "num_ctx": self.cfg.num_ctx}
        if self.cfg.num_predict > 0:
            op["num_predict"] = self.cfg.num_predict
        if self.cfg.repeat_penalty != 1.0:
            op["repeat_penalty"] = self.cfg.repeat_penalty
        return op

    def _podar(self):
        """Janela deslizante: mantém o system prompt + as últimas `max_historico`
        mensagens. Corta sempre num limite de turno (começa em 'user'), pra não
        deixar um resultado de ferramenta órfão sem a chamada que o originou."""
        limite = self.cfg.max_historico
        if limite <= 0 or len(self.messages) - 1 <= limite:
            return
        resto = self.messages[1:][-limite:]
        while resto and resto[0].get("role") != "user":
            resto.pop(0)
        self.messages = self.messages[:1] + resto

    # -------------------------------------------------- execução de ferramenta
    def _run_tool(self, name: str, args: dict) -> str:
        fn = self.dispatch.get(name)
        if fn is None:
            return f"ERRO: ferramenta '{name}' desconhecida."
        try:
            return str(fn(**(args or {})))[: self.cfg.max_tool_chars]
        except Exception as e:
            return f"ERRO ao executar {name}: {e}"

    # -------------------------------------------------- streaming (usado na CLI)
    def stream(self, user_msg: str):
        """
        Gera eventos conforme a Alice pensa:
          ("text", trecho)          -> pedaço da resposta
          ("tool", (nome, args))    -> ela chamou uma ferramenta
        """
        self.messages.append({"role": "user", "content": user_msg})
        self._podar()

        teto = getattr(self.cfg, "max_tool_rounds", 40)
        rodada = 0
        while True:  # repete enquanto a Alice pedir ferramentas
            rodada += 1
            if rodada > teto:
                yield ("text", f"\n\n[parei: atingi o limite de {teto} rodadas de ferramenta "
                               "numa só mensagem — provável loop. Me diga como seguir.]")
                return
            # segura a resposta inteira da rodada (sem mostrar token a token):
            # o modelo às vezes mistura texto normal com uma tool call em JSON
            # solto no meio ou no fim, então só dá pra saber com segurança se é
            # uma chamada de ferramenta depois que a rodada termina.
            tentativas_vazias, nudges = 0, 0
            while True:
                content, tool_calls = "", []
                for part in self.client.chat(
                    model=self.cfg.model,
                    messages=self.messages,
                    tools=self.tools_param,
                    stream=True,
                    think=False,  # modelos "thinking" (qwen3) às vezes gastam todo o
                                  # orçamento de geração "pensando" e nunca emitem o
                                  # tool_call/content de verdade — a rodada termina
                                  # vazia. Ferramentas locais já dão o raciocínio
                                  # estruturado (padrão/doc/erro); ela não precisa
                                  # deliberar em voz alta pra usá-las.
                    options=self._opcoes(),
                    keep_alive=self.cfg.keep_alive,
                ):
                    m = part["message"]
                    if m.get("content"):
                        content += m["content"]
                    if m.get("tool_calls"):
                        tool_calls += m["tool_calls"]

                if not tool_calls:
                    tool_calls = _extract_fallback_tool_calls(content)
                if tool_calls or content:
                    break  # rodada válida — segue o fluxo normal

                # Achado real rodando o teste do Raido: o Ollama às vezes gera
                # uma resposta inteira (centenas de tokens, minutos de trabalho)
                # que o parser de tool-call dele descarta por completo —
                # 'content' e 'tool_calls' voltam vazios, de forma DETERMINÍSTICA
                # pro mesmo prompt (confirmado repetindo a chamada idêntica 3x).
                # Repetir do jeito que está não adianta; um empurrão muda o
                # prompt o suficiente pra sair do resultado travado. O nudge é
                # removido do histórico depois — não é uma mensagem real.
                tentativas_vazias += 1
                if tentativas_vazias >= 3:
                    break
                self.messages.append({
                    "role": "user",
                    "content": "(sua última resposta saiu vazia — responda AGORA "
                               "com uma chamada de ferramenta ou com texto.)",
                })
                nudges += 1

            if nudges:
                del self.messages[len(self.messages) - nudges:]

            if not tool_calls and not content:
                yield ("text", "\n\n[a resposta saiu vazia mesmo depois de tentar de novo "
                               "— pode ser sobrecarga do modelo local; tente reformular ou "
                               "repetir o pedido.]")
                return

            assistant = {"role": "assistant", "content": "" if tool_calls else content}
            if tool_calls:
                # normaliza para dicts puros (os ToolCall do Ollama não são
                # serializáveis em JSON, o que quebraria salvar o histórico)
                assistant["tool_calls"] = [
                    {"function": {"name": c["function"]["name"],
                                  "arguments": c["function"]["arguments"] or {}}}
                    for c in tool_calls
                ]
            self.messages.append(assistant)

            if not tool_calls:
                if content:
                    yield ("text", content)
                return  # resposta final entregue

            for call in tool_calls:
                name = call["function"]["name"]
                args = call["function"]["arguments"] or {}
                yield ("tool", (name, args))
                result = self._run_tool(name, args)
                self.messages.append(
                    {"role": "tool", "tool_name": name, "content": result}
                )

    # -------------------------------------------------- síncrono (usado no Discord)
    def send(self, user_msg: str) -> str:
        """Roda o loop completo e devolve só o texto final."""
        return "".join(t for kind, t in self.stream(user_msg) if kind == "text")

    def reset(self):
        """Limpa o histórico, preservando o system prompt."""
        self.messages = self.messages[:1]
