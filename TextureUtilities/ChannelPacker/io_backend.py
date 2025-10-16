
""" Input processing backend: unifies system CLI and Unreal Engine so the main channel_packer logic is platform-agnostic. """
#  It is now split into two separate packages, but still allows the channel_packer function to be used interchangeably between them.






import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import unreal

from ...common_utils import log

from ..image_lib import (ImageObject, save_image as save_image_file)

from ..texture_settings import (AUTO_SAVE, PACKING_MODES)

from ..texture_utils import (get_texture_compression_settings)

from .classes import PackingMode



#                                     === Channel Packer core interface ===


def get_packing_mode_compression_map() -> Dict[str, Tuple[unreal.TextureCompressionSettings, bool]]:
# Validates the input texture compression settings from the config.
# Returns Unreal's Texture Compression Setting, its sRGB setting bool and logs whether input was correct or uses the default one.

    packing_modes: list[PackingMode] = PACKING_MODES
    compression_map: Dict[str, Tuple[unreal.TextureCompressionSettings, bool]] = {}

    for mode in packing_modes:
        mode_name: str = (mode.get("mode_name") or "").strip()

        texture_compression_settings: tuple[unreal.TextureCompressionSettings, bool, bool] = get_texture_compression_settings(mode.get("texture_compression"))
        compression_type, default_srgb, valid_texture_compression_setting = texture_compression_settings

        texture_compression_type: Optional[str] = mode.get("texture_compression")


        srgb_bool = mode.get("sRGB")
        if isinstance(srgb_bool, bool):
            srgb = srgb_bool

        elif isinstance(srgb_bool, str) and srgb_bool.strip() != "": # Input: Literal "sRGB/RGB".
            val = srgb_bool.strip().lower()
            if val == "srgb":
                srgb = True
            elif val == "rgb":
                srgb = False
            else:
                srgb = default_srgb
        else:
            srgb = default_srgb
        # Overrides the default sRGB mode with the user-set config id specified.

        compression_map[mode_name.lower()] = (compression_type, srgb)


        if not valid_texture_compression_setting and mode_name != "":
            if texture_compression_type:
                log(f"Mode '{mode_name}': Unknown texture_compression '{texture_compression_type}'. Using TC_DEFAULT.", "warn")
            else:
                log(f"Mode '{mode_name}': Empty texture_compression. Using TC_DEFAULT.", "warn")

    return compression_map


def save_generated_texture(image: ImageObject, temporary_directory: str, file_name: str, mode_name: str | None, context: "CPContext") -> None:
# Writes image to a temp file in out_dir, then imports it into the Content Browser to a corresponding folder with proper texture compression setting.
# Deletes the temp file afterward.


# Setting Texture Compression Settings per mode:
    compression_by_mode: Dict[str, Tuple[unreal.TextureCompressionSettings, bool]] = get_packing_mode_compression_map()

# Creating final paths in Content Browser:
    work_directory: str = context.work_directory
    relative_path: str = os.path.relpath(temporary_directory, work_directory).replace("\\", "/")
    if relative_path in (".", ""):
        target_package_path = "/Game"
    else:
        target_package_path = f"/Game/{relative_path.lstrip('/').lstrip('./')}"


# Writing a temporary file into out_dir:
    file_extension: str = context.export_extension
    os.makedirs(temporary_directory, exist_ok=True)
    temporary_file_path = os.path.join(temporary_directory, f"{file_name}.{file_extension}")
    try:
        save_image_file(image, temporary_file_path) # Saves the file using an image library.


# Importing the file into Unreal Engine:
        unreal.EditorAssetLibrary.make_directory(target_package_path)

        task = unreal.AssetImportTask()
        task.filename = temporary_file_path
        task.destination_path = target_package_path
        task.destination_name = file_name
        task.automated = True
        task.replace_existing = True

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])


        target_asset_path = f"{target_package_path}/{file_name}"
        imported_paths = list(task.imported_object_paths or [])

        if not imported_paths or not unreal.EditorAssetLibrary.does_asset_exist(target_asset_path):
            log(f"Couldn't import created map into Unreal: '{target_asset_path}'. Aborting.", "error")
            raise SystemExit(1)


# Setting proper compression type per mode:
        texture = unreal.EditorAssetLibrary.load_asset(target_asset_path)
        if texture:
            texture_compression_type, srgb = compression_by_mode.get(
                (mode_name or "").strip().lower(),
                (unreal.TextureCompressionSettings.TC_DEFAULT, True)  # fallback
            )

            if texture.get_editor_property("compression_settings") != texture_compression_type:
                texture.set_editor_property("compression_settings", texture_compression_type)

            if texture.get_editor_property("sRGB") != srgb:
                texture.set_editor_property("sRGB", srgb)

            if AUTO_SAVE:
                unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=True)


# Deleting a temporary file:
    finally:
        try:
            if os.path.isfile(temporary_file_path):
                os.remove(temporary_file_path)
        except Exception:
            pass