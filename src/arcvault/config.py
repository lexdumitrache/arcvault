"""~/.config/arcvault/config.toml (or $XDG_CONFIG_HOME). CLI flags override it."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from arcvault.errors import ConfigurationError

DEFAULTS: dict[str, Any] = {
    "output": "~/Documents/ArcVault",
    "deduplicate": True,
    "remove_tracking_parameters": True,
    "organization": {"enabled": True},
    "metadata": {"enrich": False},
    "ai": {"provider": None, "model": None},
}


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "arcvault" / "config.toml"


def data_dir() -> Path:
    """ArcVault-owned state (index, caches). Never inside Arc's directory.

    Private (0700): it holds titles and URLs from the library, and on macOS every local
    account is in the `staff` group that can read the home folder.
    """
    d = Path(os.environ.get("ARCVAULT_HOME", "~/.arcvault")).expanduser()
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    d.chmod(0o700)  # also tighten a folder created by an older version
    return d


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or config_path()
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    if not path.is_file():
        return cfg
    try:
        user = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigurationError(f"Invalid config {path}: {e}") from e
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg
