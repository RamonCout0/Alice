"""A Alice ouve a call: áudio do Discord → frases → texto (Whisper local).

Peças:
  • Ouvido        — sink do discord-ext-voice-recv. Recebe o Opus de cada pessoa,
                    desfaz a criptografia ponta a ponta do Discord (DAVE) quando
                    ela está ativa, e decodifica para PCM.
  • Segmentador   — junta o áudio de UMA pessoa e decide quando a frase acabou
                    (silêncio depois de fala). Puro, sem Discord: é testável.
  • Transcritor   — faster-whisper, carregado na primeira frase.

Privacidade: o áudio é transcrito na sua máquina e descartado; só o texto das
frases dirigidas à Alice entra no histórico. `/call ouvir ativa:False` desliga.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time

import numpy as np

log = logging.getLogger("alice.ouvido")

TAXA = 16000                   # o Whisper trabalha em 16 kHz mono


def para_16k_mono(pcm: bytes) -> np.ndarray:
    """PCM 48 kHz estéreo 16-bit (o que o Discord entrega) → float32 16 kHz mono."""
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if len(a) < 6:
        return np.zeros(0, dtype=np.float32)
    mono = a[: len(a) // 2 * 2].reshape(-1, 2).mean(axis=1)
    return mono[: len(mono) // 3 * 3].reshape(-1, 3).mean(axis=1)      # 48k → 16k


class Segmentador:
    """Acumula a fala de uma pessoa e entrega a frase quando ela para de falar."""

    def __init__(self, silencio_s: float = 0.8, minimo_s: float = 0.35, maximo_s: float = 18.0,
                 limiar: float = 0.012):
        self.silencio_s, self.minimo_s, self.maximo_s, self.limiar = silencio_s, minimo_s, maximo_s, limiar
        self._blocos: list[np.ndarray] = []
        self._falado = 0.0             # segundos com voz de verdade
        self._ultima_voz = 0.0
        self._total = 0.0

    def alimentar(self, audio: np.ndarray, agora: float) -> np.ndarray | None:
        if not len(audio):
            return None
        dur = len(audio) / TAXA
        com_voz = float(np.sqrt(np.mean(audio ** 2))) >= self.limiar
        if com_voz:
            self._falado += dur
            self._ultima_voz = agora
        if com_voz or self._blocos:                   # só guarda a partir da 1ª voz
            self._blocos.append(audio)
            self._total += dur
        return self._fechar() if self._total >= self.maximo_s else None

    def verificar(self, agora: float) -> np.ndarray | None:
        """Chamado por um relógio: o Discord para de mandar pacote quando a pessoa cala."""
        if self._blocos and agora - self._ultima_voz >= self.silencio_s:
            return self._fechar()
        return None

    def _fechar(self) -> np.ndarray | None:
        frase = np.concatenate(self._blocos) if self._blocos else None
        valido = self._falado >= self.minimo_s
        self._blocos, self._falado, self._total = [], 0.0, 0.0
        return frase if valido else None


class Transcritor:
    def __init__(self, cfg_escuta: dict):
        self.cfg = cfg_escuta
        self._modelo = None
        self._trava = threading.Lock()

    def _carregar(self):
        if self._modelo is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise RuntimeError("para ouvir a call instale: pip install faster-whisper") from e
            dispositivo = self.cfg.get("dispositivo", "auto")
            try:
                self._modelo = WhisperModel(self.cfg.get("modelo", "small"), device=dispositivo,
                                            compute_type="auto")
            except Exception:                         # sem CUDA/cuDNN: cai para CPU
                self._modelo = WhisperModel(self.cfg.get("modelo", "small"), device="cpu",
                                            compute_type="int8")
        return self._modelo

    def transcrever(self, audio: np.ndarray) -> str:
        with self._trava:
            segmentos, _ = self._carregar().transcribe(
                audio, language=self.cfg.get("idioma", "pt"), beam_size=1, vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=self.cfg.get("dica") or None)       # ajuda a grafar o nome dela
            return " ".join(s.text.strip() for s in segmentos if s.no_speech_prob < 0.6).strip()


# O Whisper costuma escrever o nome de vários jeitos.
_VARIANTES = {"alice": r"al[ií]-?(?:ce|ss?e|se|si|ci|s)"}


def regex_de_chamada(nomes: list[str]) -> re.Pattern:
    partes = [_VARIANTES.get(n.lower(), re.escape(n)) for n in nomes]
    return re.compile(r"\b(?:" + "|".join(partes) + r")\b", re.IGNORECASE)


# Alucinações clássicas do Whisper em trecho quase mudo.
_LIXO = re.compile(r"(?i)^(\W*|legendas? (pela|por|da) .*|obrigad[oa]( por assistir)?\.?|"
                   r"e a[ií]\.?|tchau\.?|\.+|inscreva-se.*|amara\.org.*)$")


def frase_util(texto: str) -> bool:
    return len(texto.strip()) >= 3 and not _LIXO.match(texto.strip())


def criar_ouvido(vc, loop: asyncio.AbstractEventLoop, cfg_escuta: dict, ao_ouvir):
    """Liga a escuta num VoiceRecvClient. `ao_ouvir(user_id, texto)` é uma corrotina."""
    import discord
    from discord.ext import voice_recv
    try:
        import davey
    except ImportError:
        davey = None

    transcritor = Transcritor(cfg_escuta)

    class Ouvido(voice_recv.AudioSink):
        def __init__(self):
            super().__init__()
            self.ativo = True
            self._seg: dict[int, Segmentador] = {}
            self._dec: dict[int, discord.opus.Decoder] = {}
            self._trava = threading.Lock()
            self._relogio = loop.create_task(self._vigiar())

        def wants_opus(self) -> bool:
            return True                     # queremos o Opus cru para desfazer o DAVE antes

        def write(self, user, data):
            if not self.ativo or user is None or getattr(user, "bot", False):
                return
            opus = data.opus
            if not opus:
                return
            sessao = getattr(vc._connection, "dave_session", None)
            if davey is not None and sessao is not None and getattr(sessao, "ready", False):
                try:
                    opus = sessao.decrypt(user.id, davey.MediaType.audio, opus)
                except Exception:
                    return                  # quadro de transição de chave: descarta
            try:
                with self._trava:
                    dec = self._dec.setdefault(user.id, discord.opus.Decoder())
                    pcm = dec.decode(bytes(opus), fec=False)
                    seg = self._seg.setdefault(user.id, Segmentador(
                        float(cfg_escuta.get("silencio_s", 0.8))))
                    frase = seg.alimentar(para_16k_mono(pcm), time.monotonic())
            except Exception:
                return
            if frase is not None:
                loop.call_soon_threadsafe(self._despachar, user.id, frase)

        async def _vigiar(self):
            while True:
                await asyncio.sleep(0.25)
                agora = time.monotonic()
                with self._trava:
                    prontas = [(uid, f) for uid, s in self._seg.items()
                               if (f := s.verificar(agora)) is not None]
                for uid, frase in prontas:
                    self._despachar(uid, frase)

        def _despachar(self, user_id: int, frase: np.ndarray):
            loop.create_task(self._transcrever(user_id, frase))

        async def _transcrever(self, user_id: int, frase: np.ndarray):
            try:
                texto = await asyncio.to_thread(transcritor.transcrever, frase)
            except Exception as e:
                log.warning("transcrição falhou: %s", e)
                return
            if frase_util(texto):
                await ao_ouvir(user_id, texto)

        def cleanup(self):
            self._relogio.cancel()

    ouvido = Ouvido()
    vc.listen(ouvido)
    return ouvido
