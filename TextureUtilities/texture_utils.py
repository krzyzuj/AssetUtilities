
""" Shared texture utilities used across all texture-processing modules. """


import os
import re
from collections import defaultdict
from typing import (Dict, Iterable, List, Optional, Set, Tuple)

import unreal

from ..common_utils import log

from .image_lib import close_image
from .exr_converter import (check_exr_libraries, exr_to_image)

from .texture_classes import (MapNameAndResolution, TextureMapData)
from .texture_settings import (ALLOWED_FILE_TYPES, COMPRESSION_TYPES, FILE_TYPE, SIZE_SUFFIXES, SHOW_DETAILS,TEXTURE_CONFIG, TEXTURE_PREFIXES, CompressionSettings)




def check_texture_suffix_mismatch(texture: TextureMapData) -> Optional[MapNameAndResolution]:
# Checks a single texture if its declared size suffix in the name (if present) matches its actual resolution.

    if not getattr(texture, "resolution", None):
        return None
    declared_suffix: str = (texture.suffix or "").lower().lstrip("_")
    declared_suffix = re.split(r"[-_.]", declared_suffix, maxsplit=1)[0]
    expected_suffix: str = resolution_to_suffix(texture.resolution).lower().lstrip("_")
    if declared_suffix and declared_suffix != expected_suffix:
        return MapNameAndResolution(texture.filename, texture.resolution)
    return None


def close_image_files(images: Iterable[Optional[object]]) -> None:
# Safely closes all opened images even if there is an error during image processing, prevents closing the same file twice.

    processed_ids: Set[int] = set()
    for image in images:
        if image is None:
            continue
        image_id = id(image)
        if image_id in processed_ids:
            continue
        processed_ids.add(image_id)
        try:
            close_image(image)
        except (OSError, ValueError):
            pass


def detect_size_suffix(name: str) -> str:
    # Detects size suffixes present in the map name, e.g., "2K"

    normalized_size_suffixes: List[str] = sorted(
        [size_suffix.lower() for size_suffix in SIZE_SUFFIXES if size_suffix], key=len, reverse=True)
    # Normalizes tokens to lowercase and sorts by reverse length to avoid shorter tokens matching before longer ones.
    if not normalized_size_suffixes:
        return ""
    pattern = r"(?:[\._\-])(" + "|".join(map(re.escape, normalized_size_suffixes)) + r")$"
    # Tries to match suffix variants to the map name
    matched_suffix: Optional[re.Match[str]] = re.search(pattern, name.lower())
    if matched_suffix:
        return matched_suffix.group(1)
    alt_pattern: str = r"(?:[\._\-])(" + "|".join(
        map(re.escape, normalized_size_suffixes)) + r")(?:-[a-z0-9]+)?(?=[\._\-][a-z0-9]+$)"
    alt_match: Optional[re.Match[str]] = re.search(alt_pattern, name.lower())
    return alt_match.group(1) if alt_match else ""
    # Returns the captured token e.g., '2k' if able to find one


def derive_texture_name(file_name: str) -> str:
# Extracts texture name from the file's name.

    file_name_lower: str = file_name.lower() # Normalized filename.
    separator = r"[\._\-]"
    initial_size_suffix: Optional[str] = detect_size_suffix(file_name) or "" # used to find suffixes in the style of: "_roughness_2k", "_2K-roughness", etc.

# Removing type suffix:
    found_suffix_position: Optional[int] = None
    for _, config in TEXTURE_CONFIG.items():
        for type_suffix in (s.lower() for s in config.get("suffixes", [])):
            pattern: Optional[str] = match_suffixes(file_name_lower, type_suffix, (initial_size_suffix or None))
            if not pattern:
                continue
            match: Optional[re.Match[str]] = re.search(pattern, file_name, flags = re.IGNORECASE)
            if not match:
                continue
            found_suffix_position = match.start()
            break
        if found_suffix_position is not None:
            break
    stripped_name = (file_name[:found_suffix_position] if found_suffix_position is not None else file_name).rstrip("_-.")

# Removing size suffix:
    processed_size_suffix = detect_size_suffix(stripped_name)
    if processed_size_suffix:
        stripped_name = re.sub(rf"{separator}{re.escape(processed_size_suffix)}$", "", stripped_name, flags = re.IGNORECASE)

# Removing texture prefix:
    asset_type_prefixes = [prefix.lower() for prefix in TEXTURE_PREFIXES if prefix]
    if asset_type_prefixes:
        prefixes_alt = "|".join(sorted(set(asset_type_prefixes), key=len, reverse=True))
        stripped_name = re.sub(rf"(?i)^(?:{prefixes_alt})[\._\-]+", "", stripped_name)
    #  e.g. "T_"

    return stripped_name


def ensure_asset_saved(package_path: str, *, auto_save: bool) -> bool:
# Checks if the selected asset needed by the script is saved in Content Browser.
# Assumes the object and package name are the same.
# Returns a flag if all assets are saved or not.

# Checking the file status:
    if not package_path or not package_path.startswith("/Game/"):
        return False

    if not auto_save:
        return True

# Auto-saving the file:
    object_path = package_to_object_path(package_path)
    object_ = unreal.EditorAssetLibrary.load_asset(object_path)
    package = object_.get_outermost()  # Gets asset's package.
    ok = bool(unreal.EditorLoadingAndSavingUtils.save_packages([package], only_dirty=True))
    if ok:
        return True
    return False


def export_temporary_file(asset: "unreal.Texture2D", out_directory: str, asset_name: str, package_path: str, extension:str = "png", *, exr_srgb_curve: bool = True) -> Tuple[Optional[str], bool]:

    was_float: bool = False

# default export:
    ext_norm: str = "." + extension.lstrip(".") # In case the extension is already set with the dot.
    os.makedirs(out_directory, exist_ok=True)
    final_path = os.path.join(out_directory, f"{asset_name}{ext_norm}")

    default_image = unreal.AssetExportTask()
    default_image.object = asset
    default_image.filename = final_path
    default_image.automated = True
    default_image.prompt = False
    default_image.replace_identical = True

    image_ok: bool = False
    try:
        image_ok = unreal.Exporter.run_asset_export_task(default_image)
    except Exception as e:
        image_ok = False
        if SHOW_DETAILS:
            log(f"{ext_norm} export raised exception for '{package_path}': {e}", "warn")

    if image_ok and os.path.isfile(final_path):
        return os.path.abspath(final_path).replace("\\", "/"), was_float


# .exr fallback export for 32bit textures:
    use_exr: bool = check_exr_libraries()
    if use_exr:
        log(f"Exporting the '{asset_name}' as .exr", "info")

        final_exr = os.path.join(out_directory, f"{asset_name}.exr")
        exr_image = unreal.AssetExportTask()
        exr_image.object = asset
        exr_image.filename = final_exr
        exr_image.automated = True
        exr_image.prompt = False
        exr_image.replace_identical = True

        exr_ok: bool = False
        try:
            exr_ok = unreal.Exporter.run_asset_export_task(exr_image)
        except Exception as e:
            exr_ok = False
            if SHOW_DETAILS:
                log(f"EXR export raised exception for '{package_path}': {e}", "error")

        if (not exr_ok) or (not os.path.isfile(final_exr)) or (os.path.getsize(final_exr) == 0):
            if SHOW_DETAILS:
                log(f"EXR export failed or missing file: {final_exr}", "error")
            return None, was_float

        exr_path_absolute: str = os.path.abspath(final_exr).replace("\\", "/")
        final_path: str = exr_to_image(exr_path_absolute, output_extension=extension, srgb_transform=exr_srgb_curve)

        if final_path:
            was_float = True
            return final_path, was_float

        if SHOW_DETAILS:
            log(f"EXR exported but .exr to '{extension}' conversion failed for '{package_path}'", "error")
        return None, was_float

    else:
        if SHOW_DETAILS:
            log(f"Skipping .exr file: '{asset_name}' - (OpenEXR/Numpy unavailable).", "warn")
        return None, was_float



def get_selected_assets(*, recursive: bool = False) -> List[str]:
# Sorts out the selection and run function to collect the asset's package paths accordingly.
# If folders are present in the selection, then it lists assets in folders only.

    folders: list[str] = list(unreal.EditorUtilityLibrary.get_selected_folder_paths() or [])
    if folders:
        assets_in_folders = set()
        for folder in folders:
            assets_in_folders.update(list_assets_in_folder(folder, recursive=recursive))
        return sorted(assets_in_folders)
    # Gets assets in the selected folders only.

    directly_selected:List[str] = list_selected_assets()
    if directly_selected:
        return directly_selected
    # Otherwise lists package paths of the directly selected assets.
    return []


def get_texture_compression_settings(input_setting_name: str) -> Tuple[unreal.TextureCompressionSettings, bool, bool]:
# Validates the input texture compression settings from the config.
# Returns Unreal's Texture Compression Setting, its sRGB setting bool and flags whether input was correct or uses the default one.

    input_name = (input_setting_name or "").strip()

    default_setting: CompressionSettings = COMPRESSION_TYPES.get("Default")
    default_texture_compression = default_setting.texture_compression_type
    default_srgb = default_setting.default_srgb
    valid_setting: bool = False
    # Default settings.

    if not input_name:
        return default_texture_compression, default_srgb, valid_setting


    compression_name_upper = input_name.upper()
    if compression_name_upper.startswith("TC_"):
        texture_compression_type = getattr(unreal.TextureCompressionSettings, compression_name_upper, None)
        if texture_compression_type is not None:
            setting_for_label = next(
                (setting for setting in COMPRESSION_TYPES.values() if setting.texture_compression_type == texture_compression_type),
                None
            )
            srgb_for_setting = setting_for_label.default_srgb if setting_for_label is not None else default_srgb
            valid_setting = True
            return texture_compression_type, srgb_for_setting, valid_setting

        return default_texture_compression, default_srgb, valid_setting # If TC_ compression setting input by the user is not valid.
    # e.g., when user input TC_DEFAULT instead of Default.


    for label, setting in COMPRESSION_TYPES.items():
        if label.lower() == input_name.lower():
            valid_setting = True
            return setting.texture_compression_type, setting.default_srgb, valid_setting


    return default_texture_compression, default_srgb, valid_setting # Unknown setting name


def group_paths_by_folder(keys: Iterable[str]) -> Dict[str, List[str]]:
# Builds a dictionary that groups asset package paths by their parent folder relative to /Game/ folder in Content
# Browser. Used to determine the final temporary submodule for export. Works with package and object paths. e.g.,
# Game/Textures/Brick/T_Brick_BaseColor > Textures/Brick: Game/Textures/Brick/T_Brick_Normal

    package_paths_by_folder: Dict[str, List[str]] = defaultdict(list)

    for key in keys:
        if not isinstance(key, str) or not key:
            continue

        pkg = key.split(".", 1)[0] # Normalizes paths to package paths, in case object paths are provided: /Game/A/B/Asset.Asset > Game/A/B/Asset.
        if not pkg.startswith("/Game/"):
            continue
        rel = pkg.removeprefix("/Game/")  # Gets the path to the asset relative to the root Game folder.

        parent = rel.rsplit("/", 1)[0] if "/" in rel else "" # Selects asset parent folder.
        folder_label = parent if parent else "."
        package_paths_by_folder[folder_label].append(key)

    return {g: sorted(v) for g, v in sorted(package_paths_by_folder.items(), key=lambda kv: kv[0])}


def is_asset_data(asset: unreal.AssetData, asset_type: str) -> bool:
# Returns True if the current asset type matches the selected Unreal's AssetData class.

    asset_type = (asset_type or "").strip()
    if not asset_type:
        return False

    class_path = asset.asset_class_path
    if not class_path:
        return False

    class_type_name = str(class_path.asset_name)
    return class_type_name.lower() == asset_type.lower()


def is_power_of_two(n: int) -> bool:
    # Returns True if n is a power of two (n > 0).
    return (n & (n - 1) == 0) and n != 0


def list_assets_in_folder(path: Optional[str] = None, *, recursive: bool = False) -> List[str]:
# List assets package paths for assets in the given folder.
# Either uses folders selected in Content Browser, or a specific folder from the input.
# Recursive is not used now, and left as False.

# Resolving target folder:
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    folder_paths: List[str] = []

    if isinstance(path, str) and path.strip():
        folder_paths = [normalize_content_browser_folder_path(path.strip())] # Removes the /All/ root if necessary.
    # Uses the provided path and ignores the Content Browser selection.
    else:
        content_browser_subsystem = unreal.get_editor_subsystem(unreal.ContentBrowserSubsystem)
        selected_paths = content_browser_subsystem.get_selected_paths() or []
        folder_paths = [normalize_content_browser_folder_path(str(p)) for p in selected_paths] # Removes the /All/ root if necessary.
    # Gets the folder selected in Content Browser.

    if not folder_paths:
        log("No folder path provided or folders selected.", "warn")
        return []

# Building an asset paths list from all chosen folders:
    assets_package_paths: Set[str] = set()

    for folder in folder_paths:
        asset_data_list = registry.get_assets_by_path(
            folder,
            recursive=recursive,
            include_only_on_disk_assets=False,
        )
        for asset_data in asset_data_list:
            package_name = getattr(asset_data, "package_name", None)  # e.g., /Game/.../Asset
            if package_name:
                assets_package_paths.add(str(package_name))
    #  Builds a list containing AssetData metadata for each asset in the folder

    return sorted(assets_package_paths)


def list_selected_assets() -> List[str]:
 # List assets package paths for assets selected in the Content Browser.
    selected_assets: List[unreal.AssetData] = list(unreal.EditorUtilityLibrary.get_selected_asset_data())

    assets_package_paths: Set[str] = set()
    for asset_data in selected_assets:
        package_name: str = getattr(asset_data, "package_name", None)
        if package_name:
            package_name = normalize_content_browser_folder_path(str(package_name)) # Removes the /All/ root if necessary.
            if package_name.startswith("/Game/"):
              assets_package_paths.add(str(package_name))  # e.g., /Game/.../Asset

    return sorted(assets_package_paths)


def make_output_dirs(base_directory: str, *, target_folder_name: Optional[str], backup_folder_name: Optional[str]) -> tuple[str, Optional[str]]:
# Returns the output and optional backup directories for a given base path:

    base_directory = os.path.abspath(base_directory or ".")

    target_folder_name = (target_folder_name or "").strip()

    target_folder_directory = os.path.join(base_directory, target_folder_name) if target_folder_name else base_directory
    os.makedirs(target_folder_directory, exist_ok = True)

    backup_folder_directory = None
    backup_folder_name = (backup_folder_name or "").strip()
    if backup_folder_name:
        backup_folder_directory = os.path.join(base_directory, backup_folder_name)
        os.makedirs(backup_folder_directory, exist_ok = True)

    return target_folder_directory, backup_folder_directory



def match_suffixes(name_lower: str, type_suffix: str, size_suffix: str) -> Optional[str]:
    # Takes into account different naming conventions, returns the regex pattern that matches one.
    # Type...size, size...type, ...type

    separator: str = r"[\_\-\.]"
    middle_text: str = rf"(?:{separator}[A-Za-z0-9]+)?"

    if size_suffix:
        pattern1: str = rf"{separator}{re.escape(type_suffix)}{middle_text}{separator}{re.escape(size_suffix)}$"  # type ... [middle_text] ... size
        pattern2: str = rf"{separator}{re.escape(size_suffix)}{middle_text}{separator}{re.escape(type_suffix)}$"  # size ... [middle_text] ... type
        # Pattern3 = if more variations are necessary.
        if re.search(pattern1, name_lower):
            return pattern1
        if re.search(pattern2, name_lower):
            return pattern2
        # Returns the first matching pattern string.

    only_type_suffix: str = rf"{separator}{re.escape(type_suffix)}$"
    if re.search(only_type_suffix, name_lower):
        return only_type_suffix
    # Returns this in case only the type suffix is present.
    return None


def normalize_content_browser_folder_path(folder: str) -> str:
# Normalizes the package path.
# Sometimes UE classes return paths as a /All/Game/... instead of the /Game/... e.g., unreal.EditorUtilityLibrary.get_selected_folder_paths()
    folder_path = str(folder)
    if folder_path == "/All":
        return "/"
    if folder_path.startswith("/All/"):
        return folder_path[4:]
    return folder_path


def object_to_package_path(object_path: str) -> str:
# E.g., Root/A/B/Example.Example > Root/A/B/Example

    if not isinstance(object_path, str):
        return ""
    package_path = object_path.split(":", 1)[0] # If exists, proceeds to delete the subobject from the path.
    return package_path.split(".", 1)[0]


def package_to_object_path(package_path: str) -> str:
    # Assumes the object and package name are the same.
    # E.g., Root/A/B/Example > Root/A/B/Example.Example

    if not isinstance(package_path, str):
        unreal.log_error(f"Invalid package path: {package_path}")
        return ""
    object_name: str = package_path.rsplit("/", 1)[-1]
    return f"{package_path}.{object_name}"


def resolution_to_suffix(size: Tuple[int, int]) -> str:
# Tries to match the actual image size to a size suffix.

    width = max(size)
    for threshold, label in [
        (512, "512"), (1024, "1K"), (2048, "2K"), (4096, "4K"), (8192, "8K")
    ]:
        if width <= threshold:
            return label
        # Returns the full size if it does not match any suffix threshold.
    return f"{width}px"


def validate_export_extension() -> str:
# Validates the selected output extension set in config.
# Returns lowercase ext without the "."

    allowed_extensions: set[str] = set(ALLOWED_FILE_TYPES)
    extensions_aliases: Dict[str, str] = {"jpeg": "jpg"}

    extension: str = (FILE_TYPE or "").strip().lower().lstrip(".")
    extension = extensions_aliases.get(extension, extension)

    if not extension or extension not in allowed_extensions:
        log_allowed_extensions = ", ".join(sorted(allowed_extensions))
        log(f"Invalid file type '{FILE_TYPE}' (allowed: {log_allowed_extensions}); falling back to 'png'", "warn")
        extension = "png"
    return extension