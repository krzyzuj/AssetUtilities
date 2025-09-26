
""" Shared data structures used across all texture-processing modules. """

from dataclasses import dataclass
from typing import Tuple, TypedDict




class TextureTypeConfig(TypedDict):
    suffixes: list[str] # Possible suffixes for a given texture map type, e.g., ["ao", "ambientocclusion", "occlusion", "ambient"].
    default: tuple[str, int]  # Default values for grayscale or RGB images.


#                                              === dataclasses ===

@dataclass
class MapNameAndRes:
    filename: str # Original case-sensitive filename.
    resolution: Tuple[int, int] # Texture resolution.


@dataclass
class TextureMapData:
    path: str # File path.
    resolution: Tuple[int, int] # Texture resolution.
    suffix: str # Declared size suffix.
    filename: str # Case-sensitive file name.