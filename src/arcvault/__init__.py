"""ArcVault: export, preserve, search, recover and organize your Arc browser library."""

from importlib.metadata import PackageNotFoundError, version

from arcvault.models import Resource, ResourceType, SourceType, Space
from arcvault.vault import ArcVault, Library

try:  # single source of truth: pyproject.toml
    __version__ = version("arcvault")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"
__all__ = ["ArcVault", "Library", "Resource", "ResourceType", "SourceType", "Space", "__version__"]
