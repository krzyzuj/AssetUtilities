import unreal


LOG_TYPES = ["info", "warn", "error", "skip", "complete"] # Defines log types; the backend handles printing for the Windows CLI and Unreal Engine.


def log(msg: str, kind: str = "info") -> None:
# Maps different log types to the Unreal log system.

    if msg == "":
        unreal.log("") # Print an empty line as a separation in the log.
        return
    if kind == "info":
        unreal.log(f"{msg}")
    elif kind == "warn":
        unreal.log_warning(msg)
    elif kind == "error":
        unreal.log_error(msg)
    elif kind == "skip":
        unreal.log_error(f"{msg}")
    elif kind == "complete":
        unreal.log(f"{msg}")
    else:
        unreal.log(msg)