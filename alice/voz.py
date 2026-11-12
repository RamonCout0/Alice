"""Voz em call + música.

Um único `Mixer` por servidor toca música e fala AO MESMO TEMPO: quando a
Alice fala, a música abaixa (ducking) em vez de parar.

Motores de fala (config `voz.motor`):
  • "edge"    — edge-tts (vozes neurais pt-BR, de graça, precisa de internet)
                + filtro do ffmpeg que deixa a voz aguda e sintética, estilo
                vocaloid. É um timbre ORIGINAL inspirado nesse estilo — não é
                clone de voicebank de ninguém.
  • "chipforge" — fala montada som por som com a cantora por formantes do seu
                ChipForge (vogais) + consoantes sintetizadas. Robótica, estilo
                vocaloid. Ver alice/voz_chipforge.py.
  • "externo" — qualquer sintetizador seu por linha de comando (OpenUtau,
                Piper…): `voz.comando_externo` com {texto} e {saida}.
  • "desligado"

Precisa do ffmpeg no PATH (winget install Gyan.FFmpeg).
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import threading
from collections import deque
from pathlib import Path

import discord
import numpy as np

QUADRO = 3840                      # 20 ms de PCM 48 kHz estéreo 16-bit
SILENCIO = b"\x00" * QUADRO
EXT_AUDIO = {".mp3", ".ogg", ".opus", ".wav", ".flac", ".m4a", ".webm"}


class VozIndisponivel(Exception):
    pass


def ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None


class _FonteTemp(discord.FFmpegPCMAudio):
    """Fonte de arquivo temporário: apaga o arquivo quando termina."""

    def __init__(self, caminho: str, **kw):
        super().__init__(caminho, **kw)
        self._caminho = caminho

    def cleanup(self):
        super().cleanup()
        try:
            os.remove(self._caminho)
        except OSError:
            pass


class Mixer(discord.AudioSource):
    def __init__(self):
        self.musica: discord.AudioSource | None = None
        self.falas: deque = deque()
        self.volume = 0.45
        self.pausado = False
        self.ao_fim_da_musica = None          # callable chamado (na thread do player) ao acabar
        self._trava = threading.Lock()

    def ocioso(self) -> bool:
        return self.musica is None and not self.falas

    def tocar_musica(self, fonte: discord.AudioSource):
        with self._trava:
            if self.musica:
                self.musica.cleanup()
            self.musica, self.pausado = fonte, False

    def parar_musica(self):
        with self._trava:
            if self.musica:
                self.musica.cleanup()
            self.musica = None

    def falar(self, fonte: discord.AudioSource):
        with self._trava:
            self.falas.append(fonte)

    def calar(self):
        with self._trava:
            while self.falas:
                self.falas.popleft().cleanup()

    def read(self) -> bytes:
        acabou = False
        with self._trava:
            m = b""
            if self.musica and not self.pausado:
                m = self.musica.read()
                if len(m) < QUADRO:
                    self.musica.cleanup()
                    self.musica, m, acabou = None, b"", True
            f = b""
            while self.falas and not f:
                f = self.falas[0].read()
                if len(f) < QUADRO:
                    self.falas.popleft().cleanup()
                    f = b""
            parado = self.musica is None and not self.falas
        if acabou and self.ao_fim_da_musica:
            self.ao_fim_da_musica()
        if not m and not f:
            return b"" if parado and not acabou else SILENCIO
        if not f:
            a = np.frombuffer(m, dtype=np.int16).astype(np.float32) * self.volume
        elif not m:
            return f
        else:
            a = (np.frombuffer(m, dtype=np.int16).astype(np.float32) * self.volume * 0.25
                 + np.frombuffer(f, dtype=np.int16).astype(np.float32))
        return np.clip(a, -32768, 32767).astype(np.int16).tobytes()

    def cleanup(self):
        self.parar_musica()
        self.calar()


_MD = re.compile(r"```.*?```|`[^`]*`|https?://\S+|<a?:\w+:\d+>|<[@#][!&]?\d+>", re.DOTALL)
_SIMBOLOS = re.compile(r"[*_~>#|\[\]{}\\]")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def texto_falavel(texto: str, limite: int) -> str:
    t = _EMOJI.sub("", _SIMBOLOS.sub("", _MD.sub(" ", texto or "")))
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limite:
        corte = t[:limite]
        t = corte[:max(corte.rfind("."), corte.rfind("!"), corte.rfind("?")) + 1] or corte
    return t


async def sintetizar(cfg, texto: str) -> str:
    """Gera a fala num arquivo temporário e devolve o caminho."""
    v = cfg.voz
    motor = v.get("motor", "edge")
    if motor == "desligado":
        raise VozIndisponivel("a voz está desligada no config.")
    if motor == "externo":
        cmd = v.get("comando_externo") or []
        if not cmd:
            raise VozIndisponivel("voz.comando_externo não foi configurado.")
        fd, saida = tempfile.mkstemp(suffix=".wav", prefix="alice_voz_")
        os.close(fd)
        # o texto vai como UM argumento (sem shell) — não dá pra injetar comando
        args = [a.replace("{texto}", texto).replace("{saida}", saida) for a in cmd]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, erro = await asyncio.wait_for(proc.communicate(), 120)
        except asyncio.TimeoutError:
            proc.kill()
            raise VozIndisponivel("o sintetizador externo demorou demais.")
        if proc.returncode != 0 or not os.path.getsize(saida):
            raise VozIndisponivel(f"o sintetizador externo falhou: {erro.decode('utf-8', 'replace')[-200:]}")
        return saida
    if motor == "chipforge":
        from alice import voz_chipforge
        fd, saida = tempfile.mkstemp(suffix=".wav", prefix="alice_voz_")
        os.close(fd)
        try:
            await asyncio.wait_for(asyncio.to_thread(
                voz_chipforge.falar, texto, saida, v.get("chipforge_dir", ""),
                v.get("chipforge_preset", "Solista feminina"), int(v.get("chipforge_tom", 79)),
                float(v.get("chipforge_silaba_s", 0.105))), 120)
        except Exception as e:
            os.remove(saida)
            raise VozIndisponivel(f"ChipForge: {e}") from e
        return saida
    import edge_tts
    fd, saida = tempfile.mkstemp(suffix=".mp3", prefix="alice_voz_")
    os.close(fd)
    try:
        await edge_tts.Communicate(texto, v.get("voz_edge", "pt-BR-ThalitaNeural"),
                                   pitch=v.get("tom", "+0Hz"), rate=v.get("velocidade", "+0%")).save(saida)
    except Exception as e:
        raise VozIndisponivel(f"edge-tts falhou ({type(e).__name__}) — sem internet?") from e
    return saida


def _buscar_stream(consulta: str) -> dict:
    import yt_dlp
    opcoes = {"format": "bestaudio/best", "quiet": True, "no_warnings": True, "noplaylist": True,
              "default_search": "ytsearch1", "source_address": "0.0.0.0"}
    with yt_dlp.YoutubeDL(opcoes) as y:
        info = y.extract_info(consulta, download=False)
    if "entries" in info:
        info = info["entries"][0]
    return {"titulo": info.get("title", "?"), "url": info["url"],
            "pagina": info.get("webpage_url", ""), "duracao": info.get("duration") or 0}


class SessaoVoz:
    def __init__(self, vc: discord.VoiceClient, canal_texto_id: int):
        self.vc = vc
        self.mixer = Mixer()
        self.fila: deque = deque()
        self.atual: dict | None = None
        self.canal_texto_id = canal_texto_id
        self.repetir = False
        self.ouvido = None                 # sink de escuta, quando ligado


class Voz:
    def __init__(self, bot, cfg):
        self.bot, self.cfg = bot, cfg
        self.sessoes: dict[int, SessaoVoz] = {}
        self.ao_ouvir = None               # corrotina (guild_id, user_id, texto), posta pelo bot
        self.aviso_escuta = ""

    def sessao(self, guild_id: int) -> SessaoVoz | None:
        s = self.sessoes.get(guild_id)
        if s and not s.vc.is_connected():
            self.sessoes.pop(guild_id, None)
            return None
        return s

    async def entrar(self, canal: discord.VoiceChannel, canal_texto_id: int) -> SessaoVoz:
        if not ffmpeg_ok():
            raise VozIndisponivel("o ffmpeg não está instalado/no PATH (winget install Gyan.FFmpeg).")
        s = self.sessao(canal.guild.id)
        if s:
            if s.vc.channel != canal:
                await s.vc.move_to(canal)
            s.canal_texto_id = canal_texto_id or s.canal_texto_id
            return s
        escuta = self.cfg.escuta.get("ativa") and self.ao_ouvir is not None
        cliente = discord.VoiceClient
        if escuta:
            try:
                from discord.ext import voice_recv
                cliente = voice_recv.VoiceRecvClient
            except ImportError:
                escuta = False
                self.aviso_escuta = "para ouvir a call instale: pip install discord-ext-voice-recv faster-whisper"
        vc = await canal.connect(self_deaf=not escuta, cls=cliente)
        s = self.sessoes[canal.guild.id] = SessaoVoz(vc, canal_texto_id)
        if escuta:
            from alice import ouvido
            gid = canal.guild.id

            async def ouvi(user_id: int, texto: str):
                await self.ao_ouvir(gid, user_id, texto)
            try:
                s.ouvido = ouvido.criar_ouvido(vc, self.bot.loop, self.cfg.escuta, ouvi)
            except Exception as e:
                self.aviso_escuta = f"não consegui ligar a escuta ({type(e).__name__}: {e})"
        s.mixer.ao_fim_da_musica = lambda: self.bot.loop.call_soon_threadsafe(self._proxima, canal.guild.id)
        return s

    async def sair(self, guild_id: int) -> bool:
        s = self.sessoes.pop(guild_id, None)
        if not s:
            return False
        s.mixer.cleanup()
        if s.ouvido is not None:
            try:
                s.vc.stop_listening()
            except Exception:
                pass
        await s.vc.disconnect(force=True)
        return True

    def _garantir_tocando(self, s: SessaoVoz):
        if s.vc.is_connected() and not s.vc.is_playing():
            def depois(_erro):
                if not s.mixer.ocioso() and s.vc.is_connected():
                    self.bot.loop.call_soon_threadsafe(self._garantir_tocando, s)
            s.vc.play(s.mixer, after=depois)

    async def falar(self, guild_id: int, texto: str) -> bool:
        s = self.sessao(guild_id)
        if not s:
            return False
        texto = texto_falavel(texto, int(self.cfg.voz.get("max_caracteres", 350)))
        if not texto:
            return False
        caminho = await sintetizar(self.cfg, texto)
        # o filtro "vocaloid" é só para a voz do edge; ChipForge/externo já saem prontos
        filtro = self.cfg.voz.get("filtro_ffmpeg", "") if self.cfg.voz.get("motor", "edge") == "edge" else ""
        s.mixer.falar(_FonteTemp(caminho, options=f'-af "{filtro}"' if filtro else None))
        self._garantir_tocando(s)
        return True

    def _musica_local(self, consulta: str) -> Path | None:
        pasta = Path(self.cfg.pasta_musicas) if self.cfg.pasta_musicas else None
        if not pasta or not pasta.is_dir():
            return None
        alvo = consulta.lower().strip()
        for arq in sorted(pasta.rglob("*")):
            if arq.suffix.lower() in EXT_AUDIO and alvo in arq.stem.lower():
                return arq
        return None

    def musicas_locais(self) -> list[str]:
        pasta = Path(self.cfg.pasta_musicas) if self.cfg.pasta_musicas else None
        if not pasta or not pasta.is_dir():
            return []
        return [a.stem for a in sorted(pasta.rglob("*")) if a.suffix.lower() in EXT_AUDIO]

    async def enfileirar(self, guild_id: int, consulta: str, repetir: bool = False) -> dict:
        s = self.sessao(guild_id)
        if not s:
            raise VozIndisponivel("não estou em nenhuma call — use /call entrar.")
        consulta = consulta.strip()[:200]
        local = self._musica_local(consulta)
        if local:
            faixa = {"titulo": local.stem, "arquivo": str(local), "pagina": "", "duracao": 0}
        else:
            if re.match(r"(?i)^[a-z][a-z0-9+.-]*:", consulta) and not re.match(r"(?i)^https?://", consulta):
                raise VozIndisponivel("só aceito links http(s) ou o nome da música.")
            try:
                faixa = await asyncio.wait_for(asyncio.to_thread(_buscar_stream, consulta), 40)
            except Exception as e:
                raise VozIndisponivel(f"não achei essa música ({type(e).__name__}).") from e
        faixa["repetir"] = repetir
        s.fila.append(faixa)
        if s.mixer.musica is None:
            self._proxima(guild_id)
        return faixa

    def _proxima(self, guild_id: int):
        s = self.sessao(guild_id)
        if not s:
            return
        if s.atual and s.atual.get("repetir") and s.atual.get("arquivo") and not s.fila:
            s.fila.append(s.atual)                      # trilha ambiente em loop
        if not s.fila:
            s.atual = None
            return
        s.atual = faixa = s.fila.popleft()
        if faixa.get("arquivo"):
            fonte = discord.FFmpegPCMAudio(faixa["arquivo"], options="-vn")
        else:
            fonte = discord.FFmpegPCMAudio(
                faixa["url"], options="-vn",
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5")
        s.mixer.tocar_musica(fonte)
        self._garantir_tocando(s)

    def pular(self, guild_id: int) -> bool:
        s = self.sessao(guild_id)
        if not s or s.mixer.musica is None:
            return False
        if s.atual:
            s.atual["repetir"] = False
        s.mixer.parar_musica()
        self._proxima(guild_id)
        return True

    def parar(self, guild_id: int) -> bool:
        s = self.sessao(guild_id)
        if not s:
            return False
        s.fila.clear()
        s.atual = None
        s.mixer.parar_musica()
        return True
