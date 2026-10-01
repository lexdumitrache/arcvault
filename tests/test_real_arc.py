"""Opt-in invariants against the Arc installation on this machine.

    ARCVAULT_REAL_ARC=1 pytest tests/test_real_arc.py -q

Prints counts only, never URLs or titles. Not run in CI (CI has no Arc).
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

import pytest

from arcvault import ArcVault
from arcvault.arc.reader import read_json
from arcvault.arc.schema import detect_sidebar_schema, node_type
from arcvault.config import load_config

pytestmark = pytest.mark.skipif(not os.environ.get("ARCVAULT_REAL_ARC"), reason="set ARCVAULT_REAL_ARC=1")


@pytest.fixture(scope="module")
def vault() -> ArcVault:
    return ArcVault.discover(config=load_config(Path("/nonexistent")))  # defaults, ignore user config


def test_every_saved_sidebar_tab_is_in_the_library(vault: ArcVault) -> None:
    lib = vault.scan(archive=True)
    sb = detect_sidebar_schema(read_json(vault.installation.sidebar_path))  # type: ignore[arg-type]
    tab_ids = {
        i for i, it in sb.items.items() if node_type(it) == "tab" and it["data"]["tab"].get("savedURL")
    }
    exported = {loc.id for r in lib.unique for loc in r.locations}
    assert tab_ids <= exported, f"{len(tab_ids - exported)} sidebar tabs missing"


@pytest.mark.parametrize("kw", [{}, {"archive": True}, {"archive": True, "history": True}])
def test_no_location_lost(vault: ArcVault, kw: dict[str, bool]) -> None:
    lib = vault.scan(**kw)
    assert sum(len(r.locations) for r in lib.unique) == len(lib.resources)


def test_exports_agree(vault: ArcVault, tmp_path: Path) -> None:
    lib = vault.scan()
    n_unique, n_locs = len(lib.unique), len(lib.resources)
    d = json.loads(lib.export("json", tmp_path).read_text())
    rows = list(csv.DictReader(lib.export("csv", tmp_path).open()))
    md = lib.export("markdown", tmp_path).read_text()
    bm = lib.export("html", tmp_path).read_text()
    assert len(d["resources"]) == len(rows) == n_unique
    assert len(re.findall(r"^- \[", md, re.M)) == bm.count("<DT><A") == n_locs
    # every folder (including empty ones) is a separate bookmark folder
    assert bm.count("<DT><H3>") >= len(lib.folders)
