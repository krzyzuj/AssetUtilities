
""" Shared utilities used across all asset processing modules. """

import re
from typing import Optional

import unreal

LOG_TYPES = ["info", "warn", "error", "skip", "complete"] # Defines log types; the backend handles printing for the Windows CLI and Unreal Engine.


def log(message: str, message_kind: str = "info") -> None:
# Maps different log types to the Unreal log system.

    if message == "":
        unreal.log("") # Prints an empty line as a separation in the log.
        return
    if message_kind == "info":
        unreal.log(f"{message}")
    elif message_kind == "warn":
        unreal.log_warning(message)
    elif message_kind == "error":
        unreal.log_error(message)
    elif message_kind == "skip":
        unreal.log_error(f"{message}")
    elif message_kind == "complete":
        unreal.log(f"{message}")
    else:
        unreal.log(message)


def validate_safe_folder_name(raw_folder_name: Optional[str]) -> str:
# Validates that the custom folder name doesn't include unsupported characters.

    folder_name: str = (raw_folder_name or "").strip()
    if not folder_name:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_]+", folder_name):
        log(f"Aborted: '{raw_folder_name}' is invalid. Use only letters, digits, and underscore; no spaces", "error")
        # Prints error.
        raise SystemExit(1)
    return folder_name