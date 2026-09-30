"""Lecture et vérification de la configuration (config.yaml).

C'est le SEUL endroit qui lit config.yaml. Les autres modules reçoivent un objet
`Config` déjà vérifié, avec des valeurs prêtes à l'emploi (chemins complets, nombres).
"""

# `annotations` permet d'écrire les types (`Path | None`...) sans contrainte d'ordre
# de déclaration. C'est une habitude courante en tête de fichier Python.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# Dossier racine du projet : ce fichier est dans eu4score/, la racine est donc le
# dossier parent. `resolve()` transforme le chemin en chemin absolu.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Emplacement par défaut du fichier de configuration.
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Valeurs utilisées quand une clé est absente de config.yaml.
# Toutes les clés autorisées sont listées ici : une clé inconnue dans le fichier
# (faute de frappe) est signalée au démarrage.
DEFAULTS = {
    "save_dir": "~/Documents/Paradox Interactive/Europa Universalis IV/save games",
    "autosave_file": "mp_autosave.eu4",
    "data_dir": "data",
    "parser_path": "eu4-parser/target/release/eu4-parser.exe",
    "poll_interval": 5,
    "stable_delay": 3,
}


class ConfigError(Exception):
    """Configuration absente ou invalide. Le message explique quoi corriger."""


# `@dataclass` génère automatiquement le constructeur d'une classe qui ne fait que
# regrouper des valeurs. `frozen=True` interdit de modifier ces valeurs ensuite :
# la configuration est lue une fois et ne change plus.
@dataclass(frozen=True)
class Config:
    save_dir: Path  # dossier des sauvegardes d'EU4
    autosave_file: str  # nom de l'autosave à surveiller (ex. mp_autosave.eu4)
    data_dir: Path  # racine de l'archive (saves et JSON)
    parser_path: Path  # exécutable eu4-parser
    poll_interval: float  # secondes entre deux vérifications
    stable_delay: float  # secondes sans changement = écriture terminée

    @property
    def autosave_path(self) -> Path:
        """Chemin complet de l'autosave surveillée.

        `@property` permet d'écrire `config.autosave_path` comme un simple attribut,
        alors que la valeur est calculée à partir des autres.
        """
        return self.save_dir / self.autosave_file


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Lit, complète et vérifie la configuration. Lève `ConfigError` si elle est invalide."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(
            f"fichier de configuration introuvable : {path}\n"
            "→ copiez config.example.yaml en config.yaml"
        )

    # `safe_load` lit le YAML sans exécuter de code qu'il pourrait contenir.
    # `or {}` : un fichier vide donne None, qu'on remplace par un dictionnaire vide.
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} : le fichier doit contenir des lignes « clé: valeur »")

    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ConfigError(f"{path} : clé(s) inconnue(s) : {', '.join(sorted(unknown))}")

    # Fusion : les valeurs du fichier remplacent les valeurs par défaut.
    values = {**DEFAULTS, **raw}

    # Les chemins relatifs sont relatifs au dossier du fichier de config (la racine du
    # projet), et non au dossier depuis lequel on lance la commande.
    base = path.resolve().parent
    config = Config(
        save_dir=_resolve_path(values["save_dir"], base),
        autosave_file=str(values["autosave_file"]),
        data_dir=_resolve_path(values["data_dir"], base),
        parser_path=_resolve_path(values["parser_path"], base),
        poll_interval=_positive_number(values, "poll_interval"),
        stable_delay=_positive_number(values, "stable_delay"),
    )

    # Vérifications au démarrage : mieux vaut une erreur claire tout de suite qu'un
    # plantage à la première save de la LAN.
    if not config.save_dir.is_dir():
        raise ConfigError(f"save_dir : dossier introuvable : {config.save_dir}")
    if not config.parser_path.is_file():
        raise ConfigError(
            f"parser_path : exécutable introuvable : {config.parser_path}\n"
            "→ compilez-le avec : cargo build --release --manifest-path eu4-parser/Cargo.toml"
        )
    return config


def _resolve_path(value: object, base: Path) -> Path:
    """Remplace `~` par le dossier utilisateur et rend le chemin absolu.

    Le `_` au début du nom indique une fonction interne à ce module.
    """
    p = Path(str(value)).expanduser()
    return p if p.is_absolute() else base / p


def _positive_number(values: dict, key: str) -> float:
    """Convertit values[key] en nombre strictement positif, ou lève ConfigError."""
    value = values[key]
    # `bool` est exclu car en Python, True et False sont aussi des nombres (1 et 0).
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"{key} : un nombre positif est attendu, pas {value!r}")
    return float(value)
