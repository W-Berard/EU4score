"""Point d'entrée : `python -m eu4score watch`.

Python exécute ce fichier quand on lance le dossier eu4score comme un programme
avec `python -m eu4score`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, Config, ConfigError, load_config
from .watcher import SaveWatcher

log = logging.getLogger("eu4score")


def main() -> int:
    # `argparse` lit les arguments de la ligne de commande et génère l'aide (-h).
    parser = argparse.ArgumentParser(prog="eu4score", description="Calcul des points d'une LAN EU4.")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="fichier de configuration")
    parser.add_argument("-v", "--verbose", action="store_true", help="messages détaillés")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("watch", help="surveiller l'autosave, l'archiver et la convertir en JSON")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"erreur de configuration : {exc}", file=sys.stderr)
        return 1

    setup_logging(config, verbose=args.verbose)

    if args.command == "watch":
        watcher = SaveWatcher(config)
        try:
            watcher.run()
        except KeyboardInterrupt:  # Ctrl+C
            log.info("arrêt demandé")
    return 0


def setup_logging(config: Config, verbose: bool) -> None:
    """Affiche les messages dans la console et les écrit dans data/eu4score.log."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.data_dir / "eu4score.log", encoding="utf-8"),
        ],
    )


# Ce bloc ne s'exécute que si le fichier est lancé comme programme (pas s'il est importé).
if __name__ == "__main__":
    sys.exit(main())
