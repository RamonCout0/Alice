"""Memória de longo prazo em JSON.

  dados/memoria/usuarios/<id>.json  — perfil de cada pessoa: nomes, fatos, contagem
  dados/memoria/canais/<id>.json    — falas recentes + resumo corrido do canal

Duas regras de segurança moram aqui:
  • um fato só é gravado no perfil de QUEM FALOU (o modelo não escolhe o alvo),
    então ninguém consegue "plantar" memória sobre outra pessoa;
  • fato com cara de instrução ("sempre obedeça…") é recusado — memória é
    informação sobre a pessoa, não regra de comportamento.
"""
from __future__ import annotations

import time
from pathlib import Path

from alice import armazenamento as arm
from alice import seguranca as seg
from alice.config import DADOS

DIR_USUARIOS = DADOS / "memoria" / "usuarios"
DIR_CANAIS = DADOS / "memoria" / "canais"


def _agora() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ usuários
def _arq_usuario(user_id: int) -> Path:
    return DIR_USUARIOS / f"{int(user_id)}.json"


def usuario(user_id: int) -> dict:
    return arm.ler(_arq_usuario(user_id), lambda: {
        "id": int(user_id), "nomes": [], "fatos": [], "mensagens": 0,
        "primeira_vez": _agora(), "ultima_vez": _agora()})


def tocar_usuario(user_id: int, nome: str) -> dict:
    u = usuario(user_id)
    nome = seg.limpar_nome(nome)
    if nome not in u["nomes"]:
        u["nomes"] = (u["nomes"] + [nome])[-5:]
    u["mensagens"] += 1
    u["ultima_vez"] = _agora()
    arm.gravar(_arq_usuario(user_id), u)
    return u


def lembrar(user_id: int, fato: str, maximo: int = 60) -> tuple[bool, str]:
    fato = seg.limpar(fato, 220)
    if len(fato) < 4:
        return False, "fato vazio"
    if seg.e_suspeito(fato):
        return False, "isso parece instrução, não um fato sobre a pessoa — não guardei"
    u = usuario(user_id)
    if any(f["texto"].lower() == fato.lower() for f in u["fatos"]):
        return False, "já sabia disso"
    u["fatos"].append({"texto": fato, "quando": _agora()})
    u["fatos"] = u["fatos"][-maximo:]
    arm.gravar(_arq_usuario(user_id), u)
    return True, "guardado"


def esquecer(user_id: int, trecho: str | None = None) -> int:
    """Sem trecho apaga tudo da pessoa; com trecho, só os fatos que o contêm."""
    u = usuario(user_id)
    antes = len(u["fatos"])
    if trecho:
        u["fatos"] = [f for f in u["fatos"] if trecho.lower() not in f["texto"].lower()]
    else:
        u["fatos"] = []
    arm.gravar(_arq_usuario(user_id), u)
    return antes - len(u["fatos"])


def bloco_usuario(user_id: int) -> str:
    u = usuario(user_id)
    if not u["fatos"]:
        return ""
    linhas = "\n".join(f"- {f['texto']}" for f in u["fatos"][-25:])
    return seg.embrulhar_dados(linhas, "memoria-da-pessoa", 3000)


# -------------------------------------------------------------------- canais
def _arq_canal(canal_id: int) -> Path:
    return DIR_CANAIS / f"{int(canal_id)}.json"


def canal(canal_id: int) -> dict:
    return arm.ler(_arq_canal(canal_id), lambda: {"id": int(canal_id), "resumo": "", "falas": []})


def registrar_fala(canal_id: int, papel: str, texto: str, autor: str = "",
                   autor_id: int = 0) -> dict:
    c = canal(canal_id)
    c["falas"].append({"papel": papel, "autor": autor, "autor_id": autor_id,
                       "texto": texto[:1800], "quando": _agora()})
    arm.gravar(_arq_canal(canal_id), c)
    return c


def falas_para_resumir(canal_id: int, manter: int) -> list[dict]:
    """Devolve as falas antigas que passaram do limite (sem removê-las ainda)."""
    c = canal(canal_id)
    excesso = len(c["falas"]) - manter
    return c["falas"][:excesso] if excesso >= manter // 2 else []


def aplicar_resumo(canal_id: int, novo_resumo: str, n_resumidas: int) -> None:
    c = canal(canal_id)
    c["resumo"] = seg.limpar(novo_resumo, 1500)
    c["falas"] = c["falas"][n_resumidas:]
    arm.gravar(_arq_canal(canal_id), c)


def limpar_canal(canal_id: int) -> None:
    arm.gravar(_arq_canal(canal_id), {"id": int(canal_id), "resumo": "", "falas": []})


def mensagens_do_canal(canal_id: int) -> list[dict]:
    """Histórico no formato do chat. Falas de pessoas levam o autor entre colchetes."""
    c = canal(canal_id)
    msgs = []
    if c["resumo"]:
        msgs.append({"role": "system",
                     "content": "Resumo do que já rolou neste canal:\n"
                                + seg.embrulhar_dados(c["resumo"], "resumo-do-canal", 1600)})
    for f in c["falas"]:
        if f["papel"] == "assistant":
            msgs.append({"role": "assistant", "content": f["texto"]})
        else:
            msgs.append({"role": "user", "content": f"[{f['autor']}]: {f['texto']}"})
    return msgs
