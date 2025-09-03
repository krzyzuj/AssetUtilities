
""" Shared data structures used across all texture-processing modules. """

from dataclasses import dataclass
from typing import Tuple





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