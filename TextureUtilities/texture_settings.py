
""" Global settings and constants shared across all texture modules. """

import json
from pathlib import Path
from typing import Dict, List, NamedTuple, Set
import unreal

from .texture_classes import TextureTypeConfig


class CompressionSettings(NamedTuple):
    texture_compression_type: unreal.TextureCompressionSettings
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
DEBUG: bool = _as_bool(_global_cfg.get("DEBUG", False))

# Generators:
_generators_cfg = _config_data.get("generators", {})
FILE_TYPE: str = _generators_cfg.get("FILE_TYPE", "png").strip() # File type extension for temporary texture files created outside Unreal.
UNREAL_TEMP_FOLDER: str = _generators_cfg.get("UNREAL_TEMP_FOLDER", "").strip() # Destination folder for exporting source textures for channel packing.
BACKUP_FOLDER_NAME: str = _generators_cfg.get("BACKUP_FOLDER_NAME", "").strip() # If provided, moves source maps used during generation into a backup folder after creating the channel-packed map.
EXR_SRGB_CURVE: bool = _as_bool(_generators_cfg.get("EXR_SRGB_CURVE", True)) # If true, applies sRGB gamma transform when converting the .exr, mimicking Photoshop behavior, when converting with gamma 1.0/exposure 0.0
DELETE_USED: bool = _as_bool(_generators_cfg.get("DELETE_USED", False)) # If true, deletes the files used by the function.

# Channel Packer:
_channel_cfg = _config_data.get("channel_packer", {})
RESIZE_STRATEGY: str = _channel_cfg.get("RESIZE_STRATEGY", "down").strip() # Specifies how textures are rescaled when resolutions differ within a set: down to the smallest or up to the largest.
CHANNEL_TARGET_FOLDER_NAME: str = _channel_cfg.get("TARGET_FOLDER_NAME", "").strip() # If provided, places generated channel-packed maps into a custom folder.
PACKING_MODES = _channel_cfg.get("PACKING_MODES", []) # Uses TEXTURE_CONFIG keys for texture maps to be put into channels. The packing mode is skipped if "name": is empty.

# Linear Color Curve Sampler:
_color_curve_cfg = _config_data.get("linear_color_curve_sampler", {})
SWATCH_COUNT: int = _color_curve_cfg.get("SWATCH_COUNT", 5) # Number of color swatches sampled from the image.
DIVISION_METHOD: str = _color_curve_cfg.get("DIVISION_METHOD", "perceptual").strip() # Image's lightness partitioning method: "perceptual" or "uniform".
EXPORT_PRESET: str = _color_curve_cfg.get("EXPORT_PRESET", "values").strip() # Color picking preset name: "dominant", "diverse", "values", or "all" (exports all three).
LIGHT_BAND_SIZE: int = _color_curve_cfg.get("LIGHT_BAND_SIZE", 0.5)  # Width of the lightness sample for pixel weighting; larger for more color averaging.
COLORCURVE_TARGET_FOLDER_NAME: str = _color_curve_cfg.get("TARGET_FOLDER_NAME", "").strip() # If provided, places generated curves into a custom folder.
CUSTOM_PREFIX: str = _color_curve_cfg.get("CUSTOM_PREFIX", "").strip() # Optional prefix added to the generated asset name.
STEP_TRANSITION: bool =_as_bool(_color_curve_cfg.get("STEP_TRANSITION", False))  # Uses step transitions between swatches for the created curve (instead of smooth interpolation).
USE_FULL_RESOLUTION: bool =_as_bool(_color_curve_cfg.get("USE_FULL_RESOLUTION", False)) # If False, downscales the image for speed; set True to samples at full resolution.




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

TEXTURE_PREFIXES: List[str] = ["t","tex","tx"] # Prefixes to strip when deriving a clean texture name.

