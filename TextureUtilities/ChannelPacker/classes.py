
""" Data structures and typed definitions used by the Channel Packer. """

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TypedDict, NotRequired

from ..texture_classes import TextureMapData


#                                               === TypedDicts ===

class ChannelMapping(TypedDict):
    R: Optional[str]
    G: Optional[str]
    B: Optional[str]
    A: Optional[str]


class PackingMode(TypedDict):
    mode_name: str # Packing mode name defined in the config; the mode is skipped if left empty.
    custom_suffix: str # If empty, uses a generated default suffix from the first letters of the mapped channels
    channels: ChannelMapping # Texture map types for channel packing, mapped to RGBA channels.
    texture_compression: NotRequired[str]  # Unreal-only compression setting.
    srgb: NotRequired[bool | str] # Unreal-only.


class SetEntry(TypedDict):
    texture_set_name: str # Case-sensitive texture set name after stripping type/size suffixes.
    texture_types: Dict[str, List[str]] # Recognized texture map types grouped by texture set.
    untyped: List[str]  # Files whose texture type couldn't be recognized from the filename (suffix not matched).


class TextureData(TypedDict):
    texture_set_name: str # Texture set name after stripping type/size suffixes.
    extension: str # File extension type.
    path: str # File path.
    resolution: Tuple[int, int] # Texture resolution read from the file.
    texture_type: str # Texture map type, e.g., "Albedo"
    declared_suffix: str # Declared size suffix in the filename (if present).
    filename: str # Case-sensitive filename.





#                                              === dataclasses ===

TextureMapCollection = Dict[str, TextureMapData] # Maps a texture map type to its data, e.g., "Albedo": [(path="", resolution=(,), suffix="", filename="", ext="")]
# Can include different sizes for the same map type (e.g., Albedo 2K and 4K) if a set contains both; later, only the largest is used.


@dataclass
class TextureSetInfo:
    texture_set_name: str # Case-sensitive texture set name
    texture_type: str # Texture map type, e.g., "Albedo"
    declared_suffix: str # Declared size suffix in the filename (if present).
    original_filename: str # Original case-sensitive filename.


@dataclass
class TextureSet:
    texture_set_name: str  # Case-sensitive texture set name.
    available_texture_maps: TextureMapCollection = field(default_factory=dict) # Lists texture map types found for the set as keys, with their extracted data as values (e.g., "Albedo" > {path, resolution, suffix, filename}).
    processed: bool = False # True if at least one packing mode succeeded.
    completed: bool = False # True if fully processed or skipped.

@dataclass
class ValidModeEntry:
    texture_set_name: str # Case-sensitive name of the texture set.
    mode: PackingMode  # Packing mode configuration selected for this set.
    texture_maps_for_mode: TextureMapCollection # Required maps for this set.
    packing_mode_suffix: str # Final suffix used in the output filename for this mode (custom or generated).