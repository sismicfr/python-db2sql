"""Infrastructure-level errors for configuration handling."""

from __future__ import annotations

from pathlib import Path
from typing import Union


class ConfigError(Exception):
    """Generic configuration error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigMissingError(ConfigError):
    """Specified configuration file not found."""


class ConfigUnsupportedFileExtensionError(ConfigError):
    """Unsupported file extension for configuration file."""

    def __init__(self, file_ext: str, file_path: Union[str, Path]) -> None:
        super().__init__(f"Unsupported extension {file_ext} from {file_path}")


class ConfigInvalidError(ConfigError):
    """Configuration content failed validation."""
