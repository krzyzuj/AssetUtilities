
""" Global settings and constants shared across all texture modules. """

import json
from pathlib import Path
from typing import Dict, List, NamedTuple, Set

import unreal

from .texture_classes import TextureTypeConfig

class CompressionSettings(NamedTuple):
    tex_comp_type: unreal.TextureCompressionSettings
    default_srgb: bool
# Unreal's texture compression settings.


def _as_bool(v) -> bool:
# Converts .json input (bool/int/str/None) to a real bool;
# Avoids the case where a non-empty string like "False" is treated as True.

    if isinstance(v, bool): return v
    if isinstance(v, str):
        input_str = v.strip().lower()
        if input_str == "": return False
        return input_str in ("1","true","yes","on")
    return bool(v)



#                                           === Loading JSON file ===

_BASE_DIR = Path(__file__).resolve().parents[1]
_config_path = _BASE_DIR / "config_TextureUtilities.json"
with _config_path.open("r", encoding="utf-8") as f:
    _config_data = json.load(f)


# Global Values:
_global_cfg = _config_data.get("global", {})
AUTO_SAVE: bool = _as_bool(_global_cfg.get("AUTO_SAVE", False))  # If true, auto-saves unsaved assets; otherwise logs and skips them.
SHOW_DETAILS: bool = _as_bool(_global_cfg.get("SHOW_DETAILS", False)) # If true, shows details like exact resolution when printing logs.

# Generators:
_generators_cfg = _config_data.get("generators", {})
FILE_TYPE: str = _generators_cfg.get("FILE_TYPE", "png").strip() # File type extension for temporary texture files created outside Unreal.
UNREAL_TEMP_FOLDER: str = _generators_cfg.get("UNREAL_TEMP_FOLDER", "").strip() # Destination folder for exporting source textures for channel packing.
DEST_FOLDER_NAME: str = _generators_cfg.get("DEST_FOLDER_NAME", "").strip() # If provided, places generated channel-packed maps into a custom folder.
BACKUP_FOLDER_NAME: str = _generators_cfg.get("BACKUP_FOLDER_NAME", "").strip() # If provided, moves source maps used during generation into a backup folder after creating the channel-packed map.
EXR_SRGB_CURVE: bool = _as_bool(_generators_cfg.get("EXR_SRGB_CURVE", True)) # If true, applies sRGB gamma transform when converting the .exr, mimicking Photoshop behavior, when converting with gamma 1.0/exposure 0.0
DELETE_USED: bool = _as_bool(_generators_cfg.get("DELETE_USED", False)) # If true, deletes the files used by the function.




#                                           === Constants ===

ALLOWED_FILE_TYPES: Set[str] = {"png", "jpg", "jpeg", "tga"} # Unreal's image assets export options.
SIZE_SUFFIXES: List[str] = ["512", "1k", "2k", "4k", "8k", ""]


TEXTURE_CONFIG: dict[str, TextureTypeConfig] = {
    "AO": {"suffixes": ["ambientocclusion", "occlusion", "ambient", "ao"], "default": ("G", 255)},
    "Roughness": {"suffixes": ["roughness", "roughnes", "rough", "r"], "default": ("G", 128)},
    "Metalness": {"suffixes": ["metalness", "metalnes", "metallic", "metal", "m"], "default": ("G", 0)},
    "Height": {"suffixes": ["displacement", "height", "disp", "d", "h"], "default": ("G", 0)},
    "Mask": {"suffixes": ["opacity", "alpha", "mask"], "default": ("G", 255)},
    "Translucency": {"suffixes": ["translucency", "translucent", "trans", "t"], "default": ("G", 0)},
    "Specular": {"suffixes": ["specular", "spec", "s"], "default": ("G", 128)},
    "Normal": {"suffixes": ["normal_dx", "normal_gl", "normaldx", "normalgl", "normalgl", "normal", "nor_dx", "nor_gl", "norm", "nrm", "n"], "default": ("RGB", 128)},
    "BendNormal": {"suffixes": ["bend_normal", "bendnormal", "bn"], "default": ("RGB", 128)},
    "Bump": {"suffixes": ["bump", "bp"], "default": ("G", 128)},
    "Albedo": {"suffixes": ["basecolor", "diffuse", "albedo", "color", "diff", "base", "a", "b"],  "default": ("RGB", 128)},
    "SSS": {"suffixes": ["subsurface", "sss"], "default": ("G", 0)},
    "Emissive": {"suffixes": ["emissive", "emission", "emit", "glow"], "default": ("RGB", 0)},
    "Glossiness": {"suffixes": ["glossiness", "gloss", "gl"], "default": ("G", 128)}}
# The G/RGB image type is used by validate_packing_modes to ensure that an RGB image is not mapped to a single channel without explicitly specifying the channel using .R or _R.


COMPRESSION_TYPES: Dict[str, CompressionSettings] = {
    "Default":        CompressionSettings(unreal.TextureCompressionSettings.TC_DEFAULT, True),
    "Normalmap":      CompressionSettings(unreal.TextureCompressionSettings.TC_NORMALMAP, False),
    "Masks":          CompressionSettings(unreal.TextureCompressionSettings.TC_MASKS, False),
    "Grayscale":      CompressionSettings(unreal.TextureCompressionSettings.TC_GRAYSCALE, False),
    "Displacementmap":CompressionSettings(unreal.TextureCompressionSettings.TC_DISPLACEMENTMAP, False),
}



