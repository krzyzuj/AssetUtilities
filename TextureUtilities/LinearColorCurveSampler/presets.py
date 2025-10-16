
"""Ready-made presets for extracting colors from textures, each emphasizing different color/lightness values."""

from typing import Literal
from dataclasses import dataclass


@dataclass(frozen = True)
class PresetConfig:
    LIGHTNESS_WEIGHT_METHOD: Literal["gauss", "triangle"]
    HUE_MODE: Literal["none", "dominant", "diverse"]
    HUE_WEIGHT_METHOD: Literal["gauss", "triangle", "none"]
    HUE_BAND_SIZE: float


PresetName = Literal["dominant", "diverse", "values"]
PresetOrAll = Literal["dominant", "diverse", "values", "all"]


PRESETS: dict[PresetName, PresetConfig] = {
    "dominant": PresetConfig(
        LIGHTNESS_WEIGHT_METHOD = "gauss",
        HUE_MODE = "dominant",
        HUE_WEIGHT_METHOD = "gauss",
        HUE_BAND_SIZE = 60.0,
    ),
    "diverse": PresetConfig(
        LIGHTNESS_WEIGHT_METHOD = "gauss",
        HUE_MODE = "diverse",
        HUE_WEIGHT_METHOD = "triangle",
        HUE_BAND_SIZE = 35.0,
    ),
    "values": PresetConfig(
        LIGHTNESS_WEIGHT_METHOD = "triangle",
        HUE_MODE = "none",
        HUE_WEIGHT_METHOD = "none",
        HUE_BAND_SIZE = 100.0,
    ),
}
# LIGHTNESS_WEIGHT_METHOD = "gauss" | "triangle" - lightness weighting type - gauss = smoother falloff | triangle = crisper, favors exact target lightness.
# HUE_MODE = "none" | "dominant" | "diverse" - hue diversity behavior within each lightness band - none = ignore; dominant = strongest hue; diverse = spread via repulsion.
# HUE_WEIGHT_METHOD = "none" | "gauss" | "triangle" - hue weighting type - none = hues are ignored | gauss = smoother falloff | triangle = crisper, favors exact target hue.
# HUE_BAND_SIZE = <degrees> - neighboring hues range(°) - weight falloff from the chosen hue - neighboring hues have less weight when picking swatches.


def apply_preset(preset_name: PresetName) -> PresetConfig:
# Returns the PresetConfig for a given preset name.
    try:
        return PRESETS[preset_name]
    except KeyError as e:
        raise ValueError(f"Unknown preset: {preset_name}") from e

def iter_presets(name_or_all: PresetOrAll) -> list[tuple[PresetName, PresetConfig]]:
# Turns preset name (or "all") into a list of (name, config) pairs.
    if name_or_all == "all":
        return [(preset, PRESETS[preset]) for preset in ("dominant", "diverse", "values")]
    else:
        config = apply_preset(name_or_all)
        return [(name_or_all, config)]