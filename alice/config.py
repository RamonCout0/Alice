"""Configuração da Alice: config/alice.json + variáveis de ambiente.

Segredos (token do Discord) vêm de preferência do ambiente (DISCORD_TOKEN) e
nunca são mostrados ao modelo — o módulo de segurança ainda filtra a saída.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
CONFIG_JSON = RAIZ / "config" / "alice.json"
CONFIG_EXEMPLO = RAIZ / "config" / "alice.example.json"
PERSONA_MD = RAIZ / "config" / "persona.md"


@dataclass
class Config:
    # --- cérebro (Ollama) ---
    modelo: str = "qwen3:8b"
    ollama_host: str = "http://localhost:11434"
    num_ctx: int = 8192
    temperatura: float = 0.7
    # até quantos bilhões de parâmetros o modelo conta como "pequeno": nesse
    # modo ela é empurrada a PESQUISAR (DuckDuckGo) em vez de confiar na memória.
    pequeno_ate_b: float = 9.0
    max_rodadas_ferramenta: int = 6

    # --- Discord ---
    discord_token: str = ""
    dono_id: int = 0
    confiaveis: list = field(default_factory=list)
    servidor_id: int = 0            # opcional: sincroniza os /comandos na hora
    nomes_gatilho: list = field(default_factory=lambda: ["alice"])
    rolagem_automatica: bool = True  # desligue se o bot artoniana estiver no mesmo servidor

    # --- memória ---
    historico_por_canal: int = 24    # falas recentes mantidas na íntegra
    max_fatos_por_usuario: int = 60

    # --- imagens (ComfyUI local) ---
    comfy_url: str = "http://127.0.0.1:8188"
    comfy_modelos: dict = field(default_factory=lambda: {
        "anime": "waiIllustriousSDXL_v150.safetensors",
        "realista": "juggernautXL_ragnarokBy.safetensors",
        "pixel": "waiIllustriousSDXL_v150.safetensors",
    })
    comfy_lora_pixel: str = "pixel-art-xl.safetensors"
    liberar_vram: bool = True        # descarrega o LLM antes de gerar imagem
    imagens_por_hora: int = 6        # limite por usuário comum

    # --- Gatuno de Estrelas ---
    gatuno_url: str = "https://gatunoestrelas.com.br"
    gatuno_intervalo_min: int = 15
    canal_novidades_id: int = 0

    # --- Argos ---
    argos_dir: str = ""
    argos_projetos: dict = field(default_factory=dict)   # apelido -> pasta

    # --- voz / música ---
    voz: dict = field(default_factory=lambda: {
        "motor": "edge",                      # edge | chipforge | externo | desligado
        "chipforge_dir": "",                  # pasta do clone do ChipForge (motor "chipforge")
        "chipforge_preset": "Solista feminina",
        "chipforge_tom": 79,                  # nota MIDI base (79 = sol agudo)
        "chipforge_silaba_s": 0.105,
        "voz_edge": "pt-BR-ThalitaNeural",
        "tom": "+38Hz",                       # agudo, estilo vocaloid
        "velocidade": "+8%",
        "filtro_ffmpeg": "asetrate=48000*1.06,aresample=48000,atempo=0.95,"
                         "chorus=0.6:0.9:40:0.25:0.3:2,treble=g=4",
        "comando_externo": [],                # ex.: ["python","chipforge.py","--texto","{texto}","--saida","{saida}"]
        "seguir_dono": True,
        "max_caracteres": 350,
    })
    # --- escuta da call (voz → texto, Whisper local) ---
    escuta: dict = field(default_factory=lambda: {
        "ativa": True,
        "modelo": "small",                    # tiny | base | small | medium | large-v3
        "dispositivo": "auto",                # auto usa a GPU se der; senão CPU
        "idioma": "pt",
        "precisa_chamar": True,               # só responde se disserem "Alice"…
        "janela_conversa_s": 25,              # …ou se ela acabou de falar com a pessoa
        "silencio_s": 0.8,
        "dica": "Conversa em português com a Alice. Alice, rola um dado.",
    })
    pasta_musicas: str = ""                  # trilhas locais (ex.: a pasta do rpg-song)

    # --- livros de regra indexados (python -m alice.indexar_livro) ---
    pasta_livros: str = str(DADOS / "livros")

    def nivel_de(self, user_id: int) -> int:
        from alice.seguranca import DONO, CONFIAVEL, REGULAR
        if self.dono_id and user_id == self.dono_id:
            return DONO
        if user_id in self.confiaveis:
            return CONFIAVEL
        return REGULAR


def carregar(caminho: Path | None = None) -> Config:
    origem = caminho or (CONFIG_JSON if CONFIG_JSON.exists() else CONFIG_EXEMPLO)
    dados = {}
    if origem.exists():
        dados = json.loads(origem.read_text(encoding="utf-8"))
    conhecidos = {f.name for f in fields(Config)}
    cfg = Config(**{k: v for k, v in dados.items() if k in conhecidos})
    # dicionários parciais no JSON herdam os padrões
    padrao = Config()
    cfg.voz = {**padrao.voz, **(cfg.voz or {})}
    cfg.escuta = {**padrao.escuta, **(cfg.escuta or {})}
    cfg.comfy_modelos = {**padrao.comfy_modelos, **(cfg.comfy_modelos or {})}
    cfg.discord_token = os.environ.get("DISCORD_TOKEN") or cfg.discord_token
    if os.environ.get("ALICE_DONO_ID"):
        cfg.dono_id = int(os.environ["ALICE_DONO_ID"])
    cfg.confiaveis = [int(x) for x in cfg.confiaveis]
    DADOS.mkdir(exist_ok=True)
    return cfg


def persona() -> str:
    return PERSONA_MD.read_text(encoding="utf-8").strip()
