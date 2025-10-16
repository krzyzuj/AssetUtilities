
""" Data structures and typed definitions used by the Linear Color Curve Sampler. """

from typing import Literal, Optional, TypedDict


HueModeType = Literal["none", "dominant", "diverse"]
HueWeightType = Literal["none", "gauss", "triangle"]
LightnessWeightType = Literal["gauss", "triangle"]

class SwatchResult(TypedDict, total = False):
    rank: float # Swatch number.
    target_lightness: float # 0-1 range.
    picked_color: tuple[float, float, float] # Final RGB sample color.
    pixels_used: int # DEBUG | number of pixels contributing for each swatch
    pixel_used_above_gray_threshold: int # DEBUG | number of pixels with Chroma value above a threshold.
    hue_target: Optional[float] # DEBUG | hue center of the bin with the highest hue weights [in °].