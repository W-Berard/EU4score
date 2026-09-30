"""Tests du watcher : en-tête, archivage, rattrapage, attente de fin d'écriture."""

from __future__ import annotations

import json
import threading
import time

import pytest
from conftest import make_save, requires_parser

from eu4score.watcher import SaveFormatError, SaveWatcher, archive_paths, process_save, read_header


def test_read_header(tmp_path):
    header = read_header(make_save(tmp_path / "s.eu4", "1445.7.1", "abc-123"))
    assert header.date == "1445.07.01"  # complétée par des zéros
    assert header.campaign_id == "abc-123"


def test_read_header_rejects_compressed_save(tmp_path):
    path = tmp_path / "s.eu4"
    path.write_bytes(b"PK\x03\x04...")
    with pytest.raises(SaveFormatError, match="compress_autosave"):
        read_header(path)


@requires_parser
def test_process_save_archives_then_ignores_duplicate(config):
    source = make_save(config.autosave_path, "1446.1.1")

    archived = process_save(source, config)
    assert archived is not None
    assert archived.save_path == config.data_dir / "campagne-test" / "saves" / "1446.01.01.eu4"
    assert archived.save_path.read_bytes() == source.read_bytes()
    # Le JSON est valide et contient bien les données de la save.
    data = json.loads(archived.json_path.read_text(encoding="utf-8"))
    assert data["players_countries"] == ["William", "HAB"]
    # Aucun fichier temporaire ne traîne.
    assert not list(config.data_dir.rglob("*.tmp"))

    # Même date : rien de nouveau.
    assert process_save(source, config) is None


@requires_parser
def test_catch_up_processes_rotation_and_missing_json(config):
    # Les 3 autosaves gardées par le jeu, de la plus ancienne à la plus récente.
    make_save(config.save_dir / "older_mp_autosave.eu4", "1445.1.1")
    make_save(config.save_dir / "old_mp_autosave.eu4", "1445.7.1")
    make_save(config.save_dir / "mp_autosave.eu4", "1446.1.1")

    received = []
    SaveWatcher(config, on_new_save=received.append).catch_up()
    assert [a.header.date for a in received] == ["1445.01.01", "1445.07.01", "1446.01.01"]

    # On supprime un JSON : le rattrapage suivant doit le recréer, et seulement lui.
    _, json_path = archive_paths(config.data_dir, received[1].header)
    json_path.unlink()
    received.clear()
    SaveWatcher(config, on_new_save=received.append).catch_up()
    assert [a.header.date for a in received] == ["1445.07.01"]
    assert json_path.exists()


def test_wait_until_stable_waits_for_slow_writer(config):
    path = config.autosave_path
    finished = threading.Event()

    def slow_writer():
        # Simule le jeu qui écrit la save en plusieurs fois pendant ~1 s.
        with open(path, "wb") as f:
            for _ in range(10):
                f.write(b"x" * 1000)
                f.flush()
                time.sleep(0.1)
        finished.set()

    # Le « jeu » écrit dans un thread à part, pendant que le test attend la stabilité.
    writer = threading.Thread(target=slow_writer)
    writer.start()
    time.sleep(0.05)
    assert SaveWatcher(config)._wait_until_stable(path)
    assert finished.is_set()  # la stabilité n'est détectée qu'après la fin de l'écriture
    writer.join()


@requires_parser
def test_run_detects_new_autosave(config):
    received = []
    watcher = SaveWatcher(config, on_new_save=received.append)
    # `run()` bloque : on le lance dans un thread pour pouvoir agir pendant ce temps.
    thread = threading.Thread(target=watcher.run)
    thread.start()
    try:
        time.sleep(0.2)
        make_save(config.autosave_path, "1446.1.1")
        _wait_for(lambda: len(received) == 1)
        make_save(config.autosave_path, "1446.7.1", filler=10)
        _wait_for(lambda: len(received) == 2)
    finally:
        watcher.stop()
        thread.join(timeout=5)
    assert [a.header.date for a in received] == ["1446.01.01", "1446.07.01"]


def _wait_for(condition, timeout: float = 10.0) -> None:
    """Attend qu'une condition devienne vraie, ou échoue après `timeout` secondes."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("délai dépassé")
        time.sleep(0.05)
