"""Outils partagés par les tests.

pytest charge automatiquement ce fichier. Les « fixtures » définies ici sont des
fonctions de préparation : un test qui déclare un paramètre `config` reçoit le
résultat de la fixture du même nom.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eu4score.config import PROJECT_ROOT, Config

PARSER_PATH = PROJECT_ROOT / "eu4-parser" / "target" / "release" / "eu4-parser.exe"

# Les tests qui lancent le vrai parser sont ignorés s'il n'a pas été compilé.
requires_parser = pytest.mark.skipif(not PARSER_PATH.is_file(), reason="eu4-parser non compilé")


def make_save(path: Path, date: str, campaign_id: str = "campagne-test", filler: int = 0) -> Path:
    """Écrit une petite sauvegarde texte valide. `filler` ajoute des lignes pour la grossir."""
    content = (
        "EU4txt\n"
        f"date={date}\n"
        'player="HAB"\n'
        f'campaign_id="{campaign_id}"\n'
        'players_countries={\n\t"William"\n\t"HAB"\n}\n'
        + "".join(f"filler_{i}={i}\n" for i in range(filler))
    )
    path.write_bytes(content.encode("cp1252"))
    return path


# `tmp_path` est une fixture fournie par pytest : un dossier temporaire neuf par test.
@pytest.fixture
def config(tmp_path: Path) -> Config:
    """Configuration pointant vers des dossiers temporaires, avec des délais très courts."""
    save_dir = tmp_path / "save games"
    save_dir.mkdir()
    return Config(
        save_dir=save_dir,
        autosave_file="mp_autosave.eu4",
        data_dir=tmp_path / "data",
        parser_path=PARSER_PATH,
        poll_interval=0.05,
        stable_delay=0.2,
    )
