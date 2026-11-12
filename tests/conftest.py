"""Isola os testes: nada é gravado em dados/ de verdade."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    from alice import cerebro, config, memoria
    from alice.ferramentas import gatuno, pixelart, rpg
    monkeypatch.setattr(config, "DADOS", tmp_path)
    monkeypatch.setattr(memoria, "DIR_USUARIOS", tmp_path / "memoria" / "usuarios")
    monkeypatch.setattr(memoria, "DIR_CANAIS", tmp_path / "memoria" / "canais")
    monkeypatch.setattr(rpg, "DIR_RPG", tmp_path / "rpg")
    monkeypatch.setattr(pixelart, "ARQ", tmp_path / "pixelart" / "aprendizado.json")
    monkeypatch.setattr(gatuno, "ARQ", tmp_path / "gatuno.json")
    monkeypatch.setattr(cerebro, "ARQ_GUARDA", tmp_path / "guarda.json")
    return tmp_path


@pytest.fixture
def cfg(tmp_path):
    from alice.config import Config
    return Config(dono_id=1, confiaveis=[2], pasta_livros=str(tmp_path / "livros"),
                  discord_token="tok-secreto-de-teste-123456")


@pytest.fixture
def ctx(cfg):
    from alice import seguranca as seg
    from alice.ferramentas import Contexto
    return Contexto(cfg=cfg, user_id=10, user_nome="Fulano", nivel=seg.REGULAR, guild_id=5, canal_id=7)
