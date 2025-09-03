
""" Channel Packer specific settings. """

import json
from pathlib import Path

from .classes import PackingMode, TextureTypeConfig


#                                           === Loading JSON file ===

_BASE_DIR = Path(__file__).resolve().parents[2]
_config_path = _BASE_DIR / "config_TextureUtilities.json"
with _config_path.open("r", encoding="utf-8") as f:
    _config_data = json.load(f)


# Assigning config values:
_channel_cfg = _config_data.get("channel_packer", {})

# Channel Packer:
RESIZE_STRATEGY: str = _channel_cfg.get("RESIZE_STRATEGY", "down").strip() # Specifies how textures are rescaled when resolutions differ within a set: down to the smallest or up to the largest.
BACKUP_FOLDER_NAME: str = _channel_cfg.get("BACKUP_FOLDER_NAME", "").strip() # If provided, moves source maps used during generation into a backup folder after creating the channel-packed map.
CUSTOM_FOLDER_NAME: str = _channel_cfg.get("CUSTOM_FOLDER_NAME", "created_maps").strip() # If provided, places generated channel-packed maps into a custom folder.
PACKING_MODES: list[PackingMode] = _channel_cfg.get("PACKING_MODES", []) # Uses TEXTURE_CONFIG keys for texture maps to be put into channels. The packing mode is skipped if "name": is empty.




#                                           === Constants ===

TEXTURE_CONFIG: dict[str, TextureTypeConfig] = {
    "AO": {"suffixes": ["ao", "ambientocclusion", "occlusion", "ambient"], "default": ("G", 255)},
    "Roughness": {"suffixes": ["roughness", "roughnes", "rough", "r"], "default": ("G", 128)},
    "Metalness": {"suffixes": ["metalness", "metalnes", "metallic", "metal", "m"], "default": ("G", 0)},
    "Height": {"suffixes": ["height", "disp", "displacement", "d", "h"], "default": ("G", 0)},
    "Mask": {"suffixes": ["alpha", "opacity", "mask"], "default": ("G", 255)},
    "Translucency": {"suffixes": ["translucency", "translucent", "trans", "t"], "default": ("G", 0)},
    "Specular": {"suffixes": ["specular", "spec", "s"], "default": ("G", 128)},
    "Normal": {"suffixes": ["normal", "norm", "normaldx", "normalgl", "bump", "bentnormal", "bent_normal", "n"], "default": ("RGB", 128)},
    "Albedo": {"suffixes": ["albedo", "color", "basecolor", "diffuse", "base", "a", "b"], "default": ("RGB", 128)},
    "SSS": {"suffixes": ["sss", "subsurface"], "default": ("G", 0)},
    "Emissive": {"suffixes": ["emissive", "emit", "emission", "glow"], "default": ("RGB", 0)},
    "Glossiness": {"suffixes": ["gloss", "glossiness", "gl"], "default": ("G", 128)},}
# The G/RGB image type is used by validate_packing_modes to ensure that an RGB image is not mapped to a single channel without explicitly specifying the channel using .R or _R.