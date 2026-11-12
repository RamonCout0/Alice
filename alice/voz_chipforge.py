"""Voz da Alice montada som por som com o ChipForge (github.com/RamonCout0/chipforge).

O ChipForge tem uma cantora por formantes (`chipforge/audio/voz.py`) que faz
VOGAIS. Aqui ela vira um sintetizador de fala simples, letra a letra:

  texto ──► fonemas (regras do português) ──► um som por fonema ──► .wav

  • vogais          a cantora do ChipForge, na nota da sílaba (ditongo desliza)
  • m, n, nh        a mesma cantora de boca fechada
  • s, f, x/ch, rr  ruído filtrado (chiado), cada um na sua faixa
  • z, v, j         o chiado + um zumbido de voz por baixo
  • p, t, k, b, d, g  um silêncio curto e um estalo
  • l, r            um toque rápido de vogal fraca

É síntese por regra, do tipo dos sintetizadores de fala antigos: sai robótico e
com cara de vocaloid, não natural. A melodia segue a pontuação (sobe em
pergunta, desce em ponto final).

Config (`voz`): motor="chipforge", chipforge_dir="C:/caminho/chipforge",
chipforge_preset, chipforge_tom (nota MIDI base), chipforge_silaba_s.
"""
from __future__ import annotations

import hashlib
import sys
import unicodedata
import wave
from pathlib import Path

import numpy as np

SR = 48000
VOGAIS = "aeiou"
PENTATONICA = (0, 2, 4, 7, 9)            # dó maior pentatônica: qualquer salto soa bem
MAX_FONEMAS = 420

# consoante -> (tipo, faixa de ruído em Hz, duração s, ganho)
CONSOANTES = {
    "s": ("fricativa", (4500, 9500), 0.075, 0.30), "z": ("fricativa_voz", (4500, 9500), 0.060, 0.20),
    "x": ("fricativa", (2200, 5500), 0.080, 0.34), "j": ("fricativa_voz", (2200, 5500), 0.065, 0.22),
    "f": ("fricativa", (1500, 9000), 0.065, 0.14), "v": ("fricativa_voz", (1500, 9000), 0.055, 0.11),
    "R": ("fricativa", (600, 3200), 0.060, 0.16),                       # "rr" / r inicial
    "p": ("oclusiva", (300, 1600), 0.014, 0.45), "b": ("oclusiva_voz", (300, 1600), 0.012, 0.30),
    "t": ("oclusiva", (3000, 6500), 0.014, 0.40), "d": ("oclusiva_voz", (3000, 6500), 0.012, 0.28),
    "k": ("oclusiva", (1500, 3200), 0.018, 0.45), "g": ("oclusiva_voz", (1500, 3200), 0.014, 0.30),
    "m": ("nasal", None, 0.060, 0.55), "n": ("nasal", None, 0.050, 0.50), "N": ("nasal", None, 0.065, 0.50),
    "l": ("liquida", "u", 0.045, 0.45), "L": ("liquida", "i", 0.060, 0.50), "r": ("liquida", "a", 0.022, 0.22),
}


def _sem_acento(c: str) -> str:
    return unicodedata.normalize("NFD", c)[0].lower()


def fonemas(texto: str) -> list[dict]:
    """Texto → eventos: {'vogal','final'} · {'cons': c} · {'pausa': s, 'fim': pontuação}.

    Regras de leitura do português, simplificadas: dígrafos (ch, lh, nh, rr, ss,
    qu, gu), c/g antes de e/i, s entre vogais, r inicial forte, h mudo.
    """
    t = unicodedata.normalize("NFC", texto.lower())
    eventos: list[dict] = []
    grupo = ""

    def fechar():
        nonlocal grupo
        if grupo:
            eventos.append({"vogal": grupo[0], "final": grupo[-1] if grupo[-1] != grupo[0] else ""})
            grupo = ""

    def cons(c: str):
        fechar()
        eventos.append({"cons": c})

    def vogal_em(k: int) -> bool:
        return 0 <= k < len(t) and _sem_acento(t[k]) in VOGAIS

    i = 0
    while i < len(t):
        bruto = t[i]
        c = _sem_acento(bruto)
        prox = _sem_acento(t[i + 1]) if i + 1 < len(t) else ""
        inicio = i == 0 or not t[i - 1].isalpha()
        if bruto == "ç":
            cons("s")
        elif c in VOGAIS:
            grupo += c
        elif c == "h":
            pass                                             # mudo
        elif c == "c":
            if prox == "h":
                cons("x"); i += 1
            else:
                cons("s" if prox in "ei" else "k")
        elif c == "g":
            if prox == "u" and i + 2 < len(t) and _sem_acento(t[i + 2]) in "ei":
                cons("g"); i += 1                            # "gue", "gui": o u não soa
            else:
                cons("j" if prox in "ei" else "g")
        elif c == "q":
            cons("k")
            if prox == "u" and i + 2 < len(t) and _sem_acento(t[i + 2]) in "ei":
                i += 1                                       # "que", "qui"
        elif c == "l":
            if prox == "h":
                cons("L"); i += 1
            else:
                cons("l")
        elif c == "n":
            if prox == "h":
                cons("N"); i += 1
            else:
                cons("n")
        elif c == "r":
            if prox == "r":
                cons("R"); i += 1
            else:
                cons("R" if inicio else "r")
        elif c == "s":
            if prox == "s":
                cons("s"); i += 1
            else:
                cons("z" if vogal_em(i - 1) and vogal_em(i + 1) else "s")
        elif c == "x":
            cons("x")
        elif c == "w":
            grupo += "u"
        elif c == "y":
            grupo += "i"
        elif c in "bdfjkmptvz":
            cons(c)
        else:
            fechar()
            if bruto in ".!?…\n":
                eventos.append({"pausa": 0.24, "fim": "?" if bruto == "?" else "!" if bruto == "!" else "."})
            elif bruto in ",;:—-":
                eventos.append({"pausa": 0.11, "fim": ","})
            elif bruto.isspace() and eventos and "pausa" not in eventos[-1]:
                eventos.append({"pausa": 0.04, "fim": " "})
        i += 1
    fechar()
    return eventos


def _na_escala(midi: float) -> int:
    base = int(round(midi))
    return min((base + d for d in range(-3, 4)), key=lambda n: (n % 12 not in PENTATONICA, abs(n - midi)))


def melodia(eventos: list[dict], tom: int, semente: str) -> list[dict]:
    """Dá uma nota a cada sílaba: cai devagar ao longo da frase, sobe em pergunta."""
    rng = np.random.default_rng(int(hashlib.sha256(semente.encode()).hexdigest()[:8], 16))
    saida, frase = [], []

    def fechar_frase(fim: str):
        for k, n in enumerate(frase):
            restam = len(frase) - 1 - k
            if fim == "?" and restam < 2:
                n["midi"] += 5 - 2 * restam            # sobe no fim da pergunta
            elif fim in ".!" and restam == 0:
                n["midi"] -= 4                          # repousa no fim da frase
            if fim == "!":
                n["vel"] = 118
            n["midi"] = _na_escala(n["midi"])
        frase.clear()

    for ev in eventos:
        if "vogal" in ev:
            n = {**ev, "midi": tom - min(len(frase) * 0.3, 4) + float(rng.integers(-1, 2)), "vel": 100}
            frase.append(n)
            saida.append(n)
        else:
            if ev.get("fim") in (".", "!", "?"):
                fechar_frase(ev["fim"])
            saida.append(dict(ev))
    fechar_frase(".")
    return saida


def _ruido(faixa: tuple, dur: float, rng: np.random.Generator) -> np.ndarray:
    """Ruído branco limitado a uma faixa (máscara no espectro) com entrada e saída suaves."""
    n = max(8, int(dur * SR))
    espectro = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    espectro[(freqs < faixa[0]) | (freqs > faixa[1])] = 0
    y = np.fft.irfft(espectro, n)
    y /= (np.max(np.abs(y)) or 1.0)
    borda = max(2, n // 5)
    env = np.ones(n)
    env[:borda] = np.linspace(0, 1, borda)
    env[-borda:] = np.linspace(1, 0, borda)
    return y * env


def _cantora(chipforge_dir: str, preset: str):
    raiz = str(Path(chipforge_dir).resolve())
    if not (Path(raiz) / "chipforge" / "audio" / "voz.py").is_file():
        raise FileNotFoundError(f"não achei o ChipForge em {raiz} (confira voz.chipforge_dir)")
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    from chipforge.audio.envelope import ADSR
    from chipforge.audio.voz import voz
    # ataque e soltura curtos e vibrato tardio: nota de fala, não de ária
    return voz(preset, env=ADSR(0.008, 0.03, 0.85, 0.045), vibrato_atraso_s=9.0,
               portamento_s=0.025, sopro=0.035)


def falar(texto: str, saida: str, chipforge_dir: str, preset: str = "Solista feminina",
          tom: int = 79, silaba_s: float = 0.105) -> float:
    """Renderiza o texto num .wav mono 48 kHz. Devolve a duração em segundos."""
    notas = melodia(fonemas(texto)[:MAX_FONEMAS], tom, texto)
    midis = [n["midi"] for n in notas if "vogal" in n]
    if not midis:
        raise ValueError("o texto não tem nada falável")
    cantora = _cantora(chipforge_dir, preset)
    rng = np.random.default_rng(len(texto))
    audio = np.zeros(int((len(notas) * (silaba_s + 0.06) + 1.0) * SR), dtype=np.float64)
    pos, anterior = 0, None

    def somar(trecho: np.ndarray, avanco_s: float):
        nonlocal pos
        fim = min(len(audio), pos + len(trecho))
        audio[pos:fim] += trecho[:fim - pos]
        pos += int(avanco_s * SR)

    def nota(vogal: str, final: str, midi: float, dur: float, vel: int, ganho: float = 1.0) -> np.ndarray:
        cantora.vogal, cantora.vogal_final, cantora.morph_s = vogal, final, dur * 0.8
        y = np.asarray(cantora.render_note(float(midi), dur, SR, vel, anterior), dtype=np.float64)
        return (y.mean(axis=1) if y.ndim > 1 else y) * ganho

    # a nota de uma consoante é a da próxima vogal (ou da anterior, no fim da palavra)
    proxima = [None] * len(notas)
    ultimo = midis[0]
    for k in range(len(notas) - 1, -1, -1):
        if "vogal" in notas[k]:
            ultimo = notas[k]["midi"]
        proxima[k] = ultimo

    for k, n in enumerate(notas):
        if "pausa" in n:
            pos += int(n["pausa"] * SR)
            anterior = None
        elif "vogal" in n:
            somar(nota(n["vogal"], n["final"], n["midi"], silaba_s, n["vel"]), silaba_s)
            anterior = float(n["midi"])
        else:
            tipo, extra, dur, ganho = CONSOANTES[n["cons"]]
            midi = proxima[k]
            if tipo == "nasal":
                somar(nota("m", "", midi, dur, 80, ganho), dur)
            elif tipo == "liquida":
                somar(nota(extra, "", midi, dur, 70, ganho), dur)
            elif tipo.startswith("fricativa"):
                y = _ruido(extra, dur, rng) * ganho
                if tipo.endswith("voz"):
                    z = nota("m", "", midi, dur, 70, 0.35)
                    y = y + z[:len(y)] if len(z) >= len(y) else y
                somar(y, dur * 0.85)
            else:                                           # oclusiva: silêncio + estalo
                fecho = 0.030 if tipo == "oclusiva" else 0.018
                if tipo.endswith("voz"):
                    somar(nota("m", "", midi, fecho, 60, 0.18), fecho)
                else:
                    pos += int(fecho * SR)
                somar(_ruido(extra, dur, rng) * ganho, dur)
    audio = audio[:min(len(audio), pos + int(0.15 * SR))]
    pico = float(np.max(np.abs(audio))) or 1.0
    pcm = (audio / pico * 0.8 * 32767).astype(np.int16)
    with wave.open(saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return len(pcm) / SR
