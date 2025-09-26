
""" Channel Packer specific settings. """

import json
from pathlib import Path

from .classes import PackingMode


#                                           === Loading JSON file ===

_BASE_DIR = Path(__file__).resolve().parents[2]
_config_path = _BASE_DIR / "config_TextureUtilities.json"
with _config_path.open("r", encoding="utf-8") as f:
    _config_data = json.load(f)


# Channel Packer:
_channel_cfg = _config_data.get("channel_packer", {})
RESIZE_STRATEGY: str = _channel_cfg.get("RESIZE_STRATEGY", "down").strip() # Specifies how textures are rescaled when resolutions differ within a set: down to the smallest or up to the largest.
PACKING_MODES: list[PackingMode] = _channel_cfg.get("PACKING_MODES", []) # Uses TEXTURE_CONFIG keys for texture maps to be put into channels. The packing mode is skipped if "name": is empty.




#                                           === Constants ===

