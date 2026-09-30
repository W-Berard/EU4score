"""Appel du parser Rust (eu4-parser.exe) qui convertit une sauvegarde en JSON."""

from __future__ import annotations

import subprocess
from pathlib import Path

# Durée maximale accordée au parser. Une save se convertit en ~1 s : dépasser 5 min
# signifie qu'il est bloqué.
TIMEOUT_SECONDS = 300


class ParserError(Exception):
    """Le parser a échoué. Le message reprend son explication."""


def convert_to_json(parser_path: Path, save_path: Path, json_path: Path) -> None:
    """Convertit `save_path` en JSON dans `json_path` avec eu4-parser.

    Lève `ParserError` si le parser échoue, dépasse le délai ou est introuvable.
    """
    try:
        # `subprocess.run` lance un programme externe et attend qu'il se termine,
        # comme si on tapait la commande dans un terminal :
        #   eu4-parser.exe <save> <json>
        # capture_output=True : on récupère ce que le programme affiche (dont ses
        # messages d'erreur, dans `stderr`) au lieu de le laisser s'afficher.
        # text/encoding : on lit ces messages comme du texte UTF-8 ; errors="replace"
        # évite de planter sur un caractère inattendu.
        result = subprocess.run(
            [str(parser_path), str(save_path), str(json_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ParserError(f"parser introuvable : {parser_path}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ParserError(f"parser bloqué (plus de {TIMEOUT_SECONDS} s) sur {save_path.name}") from exc

    # Le parser renvoie le code 0 en cas de succès (voir eu4-parser/src/main.rs).
    if result.returncode != 0:
        message = result.stderr.strip() or f"code de sortie {result.returncode}"
        raise ParserError(f"échec du parser sur {save_path.name} : {message}")
