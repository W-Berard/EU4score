"""Tests de la lecture de config.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest

from eu4score.config import ConfigError, load_config


def write_config(tmp_path: Path, text: str) -> Path:
    """Crée un projet factice : dossier de saves, faux parser et config.yaml."""
    (tmp_path / "saves").mkdir()
    (tmp_path / "parser.exe").write_bytes(b"")
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_relative_paths_are_resolved_from_config_dir(tmp_path):
    config = load_config(write_config(tmp_path, 'save_dir: "saves"\nparser_path: "parser.exe"\n'))
    assert config.save_dir == tmp_path / "saves"
    assert config.data_dir == tmp_path / "data"  # valeur par défaut
    assert config.autosave_path == tmp_path / "saves" / "mp_autosave.eu4"
    assert config.poll_interval == 5.0


def test_tilde_is_expanded(tmp_path, monkeypatch):
    # `monkeypatch` remplace temporairement une valeur : ici, le dossier utilisateur.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    config = load_config(write_config(tmp_path, 'save_dir: "~/saves"\nparser_path: "parser.exe"\n'))
    assert config.save_dir == tmp_path / "saves"


# `parametrize` lance le même test avec chaque jeu de valeurs de la liste.
@pytest.mark.parametrize(
    "text, message",
    [
        ('save_dir: "saves"\nparser_path: "parser.exe"\npoll_intervall: 5\n', "inconnue"),
        ('save_dir: "absent"\nparser_path: "parser.exe"\n', "save_dir"),
        ('save_dir: "saves"\nparser_path: "absent.exe"\n', "parser_path"),
        ('save_dir: "saves"\nparser_path: "parser.exe"\npoll_interval: 0\n', "poll_interval"),
        ('save_dir: "saves"\nparser_path: "parser.exe"\nstable_delay: "vite"\n', "stable_delay"),
    ],
)
def test_invalid_config_is_rejected(tmp_path, text, message):
    # `pytest.raises` vérifie que le bloc lève bien cette erreur, avec ce message.
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, text))


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="config.example.yaml"):
        load_config(tmp_path / "config.yaml")
