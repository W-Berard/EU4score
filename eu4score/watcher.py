"""Surveillance de l'autosave d'EU4, archivage des saves et conversion en JSON.

Déroulé pour chaque nouvelle autosave :
  1. attendre que le jeu ait fini de l'écrire (taille et date stables) ;
  2. la copier dans un fichier temporaire (le jeu peut la réécrire à tout moment) ;
  3. lire son en-tête : date de jeu et identifiant de campagne ;
  4. si cette date est déjà archivée : ignorer ; sinon, ranger la copie dans
     data/<campagne>/saves/<date>.eu4 ;
  5. convertir la save archivée en JSON dans data/<campagne>/json/<date>.json.

Au démarrage, un rattrapage traite les autosaves encore présentes dans le dossier du
jeu (le jeu garde les 3 dernières) et reconvertit les saves archivées sans JSON.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time

# `Callable` sert à décrire le type d'une fonction passée en paramètre.
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .parser import convert_to_json

# Journal propre à ce module. Les messages portent le nom « eu4score.watcher ».
log = logging.getLogger(__name__)

# Le jeu garde ses 3 dernières autosaves en décalant les noms à chaque nouvelle save :
# older_mp_autosave.eu4 (la plus ancienne), old_mp_autosave.eu4, mp_autosave.eu4.
# Préfixes listés de la plus ancienne à la plus récente.
ROTATION_PREFIXES = ("older_", "old_", "")

# L'en-tête utile (date, campaign_id) se trouve dans les premières lignes : inutile de
# lire les dizaines de Mo du fichier.
HEADER_BYTES = 64 * 1024

TEXT_HEADER = b"EU4txt"

# Expressions régulières (motifs de recherche) sur les octets bruts du fichier :
# - `^` = début de ligne (grâce à re.MULTILINE), donc des clés de premier niveau ;
# - `(\d+)` capture un nombre, `([^"]+)` capture tout jusqu'au guillemet suivant.
_DATE_RE = re.compile(rb"^date=(\d+)\.(\d+)\.(\d+)", re.MULTILINE)
_CAMPAIGN_RE = re.compile(rb'^campaign_id="([^"]+)"', re.MULTILINE)


class SaveFormatError(Exception):
    """Le fichier n'est pas une sauvegarde texte lisible."""


class SaveChangedError(Exception):
    """Le jeu a modifié l'autosave pendant qu'on la copiait : la copie est inutilisable."""


@dataclass(frozen=True)
class SaveHeader:
    """Informations lues au début d'une sauvegarde."""

    date: str  # date de jeu complétée par des zéros, ex. "1446.01.01" (tri chronologique)
    campaign_id: str  # identifiant de la partie, identique dans toutes ses saves


@dataclass(frozen=True)
class ArchivedSave:
    """Une save rangée dans l'archive, avec son JSON."""

    header: SaveHeader
    save_path: Path
    json_path: Path


def read_header(path: Path) -> SaveHeader:
    """Lit la date de jeu et l'identifiant de campagne au début de la sauvegarde."""
    # "rb" = lecture en octets bruts : les saves sont en windows-1252, pas en UTF-8.
    # `with` ferme automatiquement le fichier à la fin du bloc.
    with open(path, "rb") as f:
        head = f.read(HEADER_BYTES)

    if not head.startswith(TEXT_HEADER):
        raise SaveFormatError(
            f"{path.name} : pas une sauvegarde texte (compressée ou ironman ?). "
            "Vérifiez compress_autosave=no dans le settings.txt d'EU4."
        )

    date_match = _DATE_RE.search(head)
    campaign_match = _CAMPAIGN_RE.search(head)
    if not date_match or not campaign_match:
        raise SaveFormatError(f"{path.name} : date ou campaign_id introuvable dans l'en-tête")

    year, month, day = (int(g) for g in date_match.groups())
    # Le campaign_id sert de nom de dossier : on ne garde que des caractères sûrs.
    campaign_id = re.sub(r"[^A-Za-z0-9-]", "_", campaign_match.group(1).decode("ascii", "replace"))
    # `:04d` / `:02d` : entier complété par des zéros sur 4 / 2 chiffres.
    return SaveHeader(date=f"{year:04d}.{month:02d}.{day:02d}", campaign_id=campaign_id)


def archive_paths(data_dir: Path, header: SaveHeader) -> tuple[Path, Path]:
    """Chemins de la save et du JSON archivés pour cette date de cette campagne."""
    campaign_dir = data_dir / header.campaign_id
    return campaign_dir / "saves" / f"{header.date}.eu4", campaign_dir / "json" / f"{header.date}.json"


def process_save(source: Path, config: Config) -> ArchivedSave | None:
    """Archive `source` et la convertit en JSON.

    Renvoie l'`ArchivedSave` si quelque chose de nouveau a été fait (save archivée ou
    JSON créé), ou None si cette date était déjà entièrement archivée.
    """
    started = time.perf_counter()

    # 1. Copie vers un fichier temporaire, placé dans data_dir pour pouvoir ensuite le
    #    déplacer instantanément vers l'archive (même disque).
    incoming = config.data_dir / "incoming.eu4.tmp"
    incoming.parent.mkdir(parents=True, exist_ok=True)
    before = _signature(source)
    shutil.copyfile(source, incoming)
    if _signature(source) != before:
        incoming.unlink(missing_ok=True)
        raise SaveChangedError(f"{source.name} modifiée pendant la copie")

    # `try / finally` : le bloc `finally` s'exécute toujours, même en cas d'erreur.
    # Ici, il garantit que le fichier temporaire ne traîne pas.
    try:
        header = read_header(incoming)
        save_path, json_path = archive_paths(config.data_dir, header)
        save_is_new = not save_path.exists()
        if save_is_new:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            # `os.replace` déplace le fichier en une seule opération : l'archive ne
            # contient jamais de save à moitié copiée.
            os.replace(incoming, save_path)
    finally:
        incoming.unlink(missing_ok=True)

    json_is_new = not json_path.exists()
    if json_is_new:
        _convert_atomically(config.parser_path, save_path, json_path)

    if not (save_is_new or json_is_new):
        return None

    elapsed = time.perf_counter() - started
    log.info("%s : save archivée et convertie en %.1f s", header.date, elapsed)
    return ArchivedSave(header, save_path, json_path)


def repair_missing_json(config: Config) -> list[ArchivedSave]:
    """Convertit les saves archivées qui n'ont pas de JSON (ex. parser en échec)."""
    repaired = []
    # `glob("*/saves/*.eu4")` : toutes les saves de toutes les campagnes.
    # `sorted` : dans l'ordre alphabétique, donc chronologique grâce aux zéros.
    for save_path in sorted(config.data_dir.glob("*/saves/*.eu4")):
        json_path = save_path.parent.parent / "json" / f"{save_path.stem}.json"
        if json_path.exists():
            continue
        try:
            _convert_atomically(config.parser_path, save_path, json_path)
        except Exception:
            log.exception("échec de la conversion de %s", save_path)
            continue
        log.info("%s : JSON manquant recréé", save_path.stem)
        header = SaveHeader(date=save_path.stem, campaign_id=save_path.parent.parent.name)
        repaired.append(ArchivedSave(header, save_path, json_path))
    return repaired


def _convert_atomically(parser_path: Path, save_path: Path, json_path: Path) -> None:
    """Convertit en JSON via un fichier temporaire, renommé seulement en cas de succès.

    Ainsi, un JSON présent dans l'archive est forcément complet.
    """
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = json_path.with_name(json_path.name + ".tmp")
    try:
        convert_to_json(parser_path, save_path, tmp)
        os.replace(tmp, json_path)
    finally:
        tmp.unlink(missing_ok=True)


def _signature(path: Path) -> tuple[int, int] | None:
    """(taille, date de modification) du fichier, ou None s'il est absent ou vide.

    Deux signatures identiques à quelques secondes d'intervalle = fichier stable.
    """
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    if st.st_size == 0:
        return None
    return st.st_size, st.st_mtime_ns


class SaveWatcher:
    """Surveille l'autosave et archive chaque nouvelle save.

    `run()` bloque jusqu'à l'arrêt (Ctrl+C, ou `stop()`). `on_new_save`, si fourni,
    est appelé pour chaque save archivée : c'est là que se branchera la suite de
    l'application (extraction, règles, base de données).
    """

    def __init__(self, config: Config, on_new_save: Callable[[ArchivedSave], None] | None = None):
        self.config = config
        self.on_new_save = on_new_save
        # `Event` est un simple drapeau « arrêt demandé ». Son `wait(délai)` sert de
        # pause interrompable : il rend la main dès que `stop()` est appelé.
        self._stop = threading.Event()

    def stop(self) -> None:
        """Demande l'arrêt de `run()`."""
        self._stop.set()

    def run(self) -> None:
        path = self.config.autosave_path
        log.info("surveillance de %s (toutes les %g s)", path, self.config.poll_interval)
        self.catch_up()

        last = _signature(path)
        # `wait` renvoie True si l'arrêt a été demandé, False quand le délai expire :
        # la boucle tourne donc une fois par intervalle, jusqu'à l'arrêt.
        while not self._stop.wait(self.config.poll_interval):
            current = _signature(path)
            if current is None or current == last:
                continue  # pas de fichier, ou pas de changement
            if not self._wait_until_stable(path):
                continue  # arrêt demandé pendant l'attente
            # On retient la version traitée même en cas d'échec : une erreur ne doit pas
            # être retentée toutes les 5 s. Le rattrapage au prochain démarrage s'en chargera.
            last = _signature(path)
            self._handle(path)

    def catch_up(self) -> None:
        """Rattrapage : JSON manquants, puis autosaves encore présentes dans le dossier du jeu."""
        for archived in repair_missing_json(self.config):
            self._notify(archived)
        for prefix in ROTATION_PREFIXES:
            path = self.config.save_dir / f"{prefix}{self.config.autosave_file}"
            if path.exists() and self._wait_until_stable(path):
                self._handle(path)

    def _handle(self, path: Path) -> None:
        """Traite une save sans jamais laisser une erreur arrêter la surveillance."""
        try:
            archived = process_save(path, self.config)
        except SaveChangedError as exc:
            log.warning("%s : elle sera traitée à la prochaine vérification", exc)
            return
        except Exception:
            # `log.exception` affiche le message ET le détail technique de l'erreur.
            log.exception("échec du traitement de %s", path.name)
            return
        if archived is None:
            log.debug("%s : déjà archivée", path.name)
        else:
            self._notify(archived)

    def _notify(self, archived: ArchivedSave) -> None:
        if self.on_new_save is None:
            return
        try:
            self.on_new_save(archived)
        except Exception:
            log.exception("erreur dans le traitement de la save %s", archived.header.date)

    def _wait_until_stable(self, path: Path) -> bool:
        """Attend que le fichier n'ait plus changé pendant `stable_delay` secondes.

        Renvoie False si l'arrêt est demandé entre-temps.
        """
        previous = _signature(path)
        while not self._stop.wait(self.config.stable_delay):
            current = _signature(path)
            if current is not None and current == previous:
                return True
            previous = current
        return False
