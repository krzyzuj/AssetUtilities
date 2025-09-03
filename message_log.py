import unreal
from typing import List, Tuple, Optional



ASSET_CHECK_CATEGORY = "AssetCheck"  # to jest nazwa zakładki w Message Log

# Ścieżka do "kotwicy" dla walidatora (zwykły, mały asset – może być Material)
ANCHOR_PKG_DIR = "/Game/_CP_Logs"
ANCHOR_NAME = "CP_LogAnchor"

# Mapowanie z naszego "kind" -> MessageSeverity
SEVERITY_MAP = {
    "info": unreal.MessageSeverity.INFO,
    "complete": unreal.MessageSeverity.INFO,
    "warn": unreal.MessageSeverity.WARNING,
    "skip": unreal.MessageSeverity.WARNING,
    "error": unreal.MessageSeverity.ERROR,
}

# Globalny singleton walidatora
_validator_instance = None
_anchor_asset = None


class ChannelPackerLogger(unreal.AssetValidator):
    """
    Minimalny walidator, który zamienia wpisy z kolejki na AssetValidationResult,
    żeby Message Log (Asset Check) je wyświetlił.
    """
    def __init__(self):
        super().__init__()
        self._queue: List[Tuple[str, unreal.MessageSeverity]] = []

    # Nie chcemy automatycznie walidować wszystkiego – będziemy wyzwalać ręcznie.
    def can_validate(self, asset: unreal.Object) -> bool:
        return True  # pozwólmy na validate dowolnego assetu (anchor)

    def validate(self, asset: unreal.Object):
        results = []
        # Zrzucamy całą kolejkę na wynik
        while self._queue:
            msg, sev = self._queue.pop(0)
            r = unreal.AssetValidationResult()
            r.asset = asset
            r.is_valid = sev != unreal.MessageSeverity.ERROR
            r.message = msg
            r.message_severity = sev
            results.append(r)
        return results

    def enqueue(self, msg: str, sev: unreal.MessageSeverity):
        self._queue.append((msg, sev))


def _ensure_anchor_asset() -> Optional[unreal.Object]:
    """
    Tworzy / ładuje prosty asset-kotwicę, do którego będziemy „przyczepiać”
    wpisy walidatora, żeby trafiły do Asset Check.
    """
    global _anchor_asset
    if _anchor_asset and unreal.EditorAssetLibrary.is_valid(_anchor_asset):
        return _anchor_asset

    unreal.EditorAssetLibrary.make_directory(ANCHOR_PKG_DIR)
    anchor_path = f"{ANCHOR_PKG_DIR}/{ANCHOR_NAME}"

    # Jeśli istnieje – ładujemy
    if unreal.EditorAssetLibrary.does_asset_exist(anchor_path):
        _anchor_asset = unreal.EditorAssetLibrary.load_asset(anchor_path)
        return _anchor_asset

    # Jeśli nie – tworzymy malutki Material jako kotwicę
    at = unreal.AssetToolsHelpers.get_asset_tools()
    try:
        _anchor_asset = at.create_asset(
            asset_name=ANCHOR_NAME,
            package_path=ANCHOR_PKG_DIR,
            asset_class=unreal.Material,
            factory=unreal.MaterialFactoryNew()
        )
    except Exception:
        _anchor_asset = None

    return _anchor_asset


def _ensure_validator_registered() -> ChannelPackerLogger:
    global _validator_instance
    if _validator_instance is not None:
        return _validator_instance

    _validator_instance = ChannelPackerLogger()
    subsys = unreal.get_editor_subsystem(unreal.EditorValidatorSubsystem)
    subsys.add_validator(_validator_instance)
    return _validator_instance


def emit_to_asset_check(msg: str, kind: str = "info"):
    """
    Główna funkcja: dodaj komunikat do kolejki i natychmiast wyzwól walidację na anchorze.
    """
    sev = SEVERITY_MAP.get(kind, unreal.MessageSeverity.INFO)
    validator = _ensure_validator_registered()
    validator.enqueue(msg, sev)

    anchor = _ensure_anchor_asset()
    if anchor is None:
        # Awaryjnie spadamy do zwykłych logów
        unreal.log_warning(f"[AssetCheck Fallback] {msg}")
        return

    subsys = unreal.get_editor_subsystem(unreal.EditorValidatorSubsystem)
    # Wyzwalamy walidację tylko na anchorze – to spowoduje zrzut kolejki do Message Log
    try:
        subsys.validate_assets([anchor])
    except Exception as e:
        unreal.log_warning(f"[AssetCheck Fallback] {msg} (validate_assets failed: {e})")