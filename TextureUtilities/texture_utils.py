
""" Shared texture utilities used across all texture-processing modules. """

import os
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

import unreal


from .image_lib import close_image

from .texture_classes import (MapNameAndRes, TextureMapData)
from .texture_settings import (ALLOWED_FILE_TYPES, COMPRESSION_TYPES, FILE_TYPE, SIZE_SUFFIXES, UNREAL_TEMP_FOLDER, CompressionSettings)


LOG_TYPES = ["info", "warn", "error", "skip", "complete"] # Defines log types; the backend handles printing for the Windows CLI and Unreal Engine.

def log(msg: str, kind: str = "info") -> None:
# Maps different log types to the Unreal log system.

    if msg == "":
        unreal.log("") # Print an empty line as a separation in the log.
        return
    if kind == "info":
        unreal.log(f"{msg}")
    elif kind == "warn":
        unreal.log_warning(msg)
    elif kind == "error":
        unreal.log_error(msg)
    elif kind == "skip":
        unreal.log_error(f"{msg}")
    elif kind == "complete":
        unreal.log(f"{msg}")
    else:
        unreal.log(msg)


def check_texture_suffix_mismatch(tex: TextureMapData) -> Optional[MapNameAndRes]:
# Checks a single texture if its declared size suffix in the name (if present) matches its actual resolution.

    if not getattr(tex, "resolution", None):
        return None
    declared_suffix = (tex.suffix or "").lower().lstrip("_")
    expected_suffix = resolution_to_suffix(tex.resolution).lower().lstrip("_")
    if declared_suffix and declared_suffix != expected_suffix:
        return MapNameAndRes(tex.filename, tex.resolution)
    return None


def close_image_files(images: Iterable[Optional[object]]) -> None:
# Safely closes all opened images even if there is an error during image processing.

    seen: Set[int] = set()
    for im in images:
        if im is None:
            continue
        oid = id(im)
        if oid in seen:
            continue
        seen.add(oid)
        try:
            close_image(im) # Function from image_lib
        except (OSError, ValueError):
            pass


def detect_size_suffix(name: str) -> str:
    # Detects size suffixes present in the map name, e.g., "2K"

    tokens: List[str] = sorted([s.lower() for s in SIZE_SUFFIXES if s], key=len, reverse=True)
    # Normalizes tokens to lowercase and sorts by reverse length to avoid shorter tokens matching before longer ones.
    if not tokens:
        return ""
    pattern = r"(?:[\._\-])(" + "|".join(map(re.escape, tokens)) + r")$"
    # Tries to match suffix variances to the map name
    m: Optional[re.Match[str]] = re.search(pattern, name.lower())
    return m.group(1) if m else ""
    # Returns the captured token e.g., '2k' if able to find one


def ensure_asset_saved(pkg_path: str, *, auto_save: bool) -> bool:
# Checks if the selected asset needed by the script is saved in Content Browser.
# Assumes the object and package name are the same.
# Returns a flag if all assets are saved or not.

# Checking the file status:
    if not pkg_path or not pkg_path.startswith("/Game/"):
        return False

    if not auto_save:
        return True

# Auto-saving the file:
    obj_path = package_to_object_path(pkg_path)
    obj = unreal.EditorAssetLibrary.load_asset(obj_path)
    pkg = obj.get_outermost()  # Gets asset's package.
    ok = bool(unreal.EditorLoadingAndSavingUtils.save_packages([pkg], only_dirty=True))
    if ok:
        return True
    return False


def get_selected_assets(*, recursive: bool = False) -> List[str]:
# Sorts out the selection and run function to collect the asset's package paths accordingly.
# If folders are present in the selection, then it lists assets in folders only.

    folders = unreal.EditorUtilityLibrary.get_selected_folder_paths() or []
    if folders:
        collected = set()
        for f in folders:
            collected.update(list_assets_in_folder(f, recursive=recursive))
        return sorted(collected)
    # Gets assets in the selected folders only.

    direct:List[str] = list_selected_assets()
    if direct:
        return direct
    # Otherwise lists package paths of the directly selected assets.
    return []


def get_tex_compression_settings(input_setting_name: str) -> Tuple[unreal.TextureCompressionSettings, bool, bool]:
# Validates the input texture compression settings from the config.
# Returns Unreal's Texture Compression Setting, its's sRGB setting bool and flags whether input was correct or uses the default one.

    input_name = (input_setting_name or "").strip()

    default_setting: CompressionSettings = COMPRESSION_TYPES.get("Default")
    default_tex_comp = default_setting.tex_comp_type
    default_srgb = default_setting.default_srgb
    valid_setting: bool = False
    # Default settings.

    if not input_name:
        return default_tex_comp, default_srgb, valid_setting


    upper = input_name.upper()
    if upper.startswith("TC_"):
        tex_comp_type = getattr(unreal.TextureCompressionSettings, upper, None)
        if tex_comp_type is not None:
            setting_for_label = next(
                (setting for setting in COMPRESSION_TYPES.values() if setting.tex_comp_type == tex_comp_type),
                None
            )
            srgb_for_setting = setting_for_label.default_srgb if setting_for_label is not None else default_srgb
            valid_setting = True
            return tex_comp_type, srgb_for_setting, valid_setting

        return default_tex_comp, default_srgb, valid_setting # If TC_ compression setting input by the user is not valid.
    # e.g., when user input TC_DEFAULT instead of Default.


    for label, setting in COMPRESSION_TYPES.items():
        if label.lower() == input_name.lower():
            valid_setting = True
            return setting.tex_comp_type, setting.default_srgb, valid_setting


    return default_tex_comp, default_srgb, valid_setting # Unknown setting name


def group_paths_by_folder(keys: Iterable[str]) -> Dict[str, List[str]]:
# Builds a dictionary that groups asset package paths by their parent folder relative to /Game/ folder in Content
# Browser. Used to determine the final temporary submodule for export. Works with package and object paths. e.g.,
# Game/Textures/Brick/T_Brick_BaseColor > Textures/Brick: Game/Textures/Brick/T_Brick_Normal

    groups: Dict[str, List[str]] = defaultdict(list)

    for key in keys:
        if not isinstance(key, str) or not key:
            continue

        pkg = key.split(".", 1)[0] # Normalizes paths to package paths, in case object paths are provided: /Game/A/B/Asset.Asset > Game/A/B/Asset.
        if not pkg.startswith("/Game/"):
            continue
        rel = pkg.removeprefix("/Game/")  # Gets the path to the asset relative to the root Game folder.

        parent = rel.rsplit("/", 1)[0] if "/" in rel else "" # Selects asset parent folder.
        label = parent if parent else "."
        groups[label].append(key)

    return {g: sorted(v) for g, v in sorted(groups.items(), key=lambda kv: kv[0])}


def is_asset_data(asset: unreal.AssetData, asset_type: str) -> bool:
# Returns True if the current asset type matches the selected Unreal's AssetData class.

    at = (asset_type or "").strip()
    if not at:
        return False

    class_path = asset.asset_class_path
    if not class_path:
        return False

    cls_name = str(class_path.asset_name)
    return cls_name.lower() == at.lower()


def is_power_of_two(n: int) -> bool:
    # Returns True if n is a power of two (n > 0).
    return (n & (n - 1) == 0) and n != 0


def list_assets_in_folder(path: Optional[str] = None, *, recursive: bool = False) -> List[str]:
# List assets package paths for assets in the given folder.
# Either uses folders selected in Content Browser, or a specific folder from the input.
# Recursive is not used now, and left as False.

# Resolving target folder:
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    folders: List[str] = []

    if isinstance(path, str) and path.strip():
        folders = [normalize_cb_folder(path.strip())] # Removes the /All/ root if necessary.
    # Uses the provided path and ignores the Content Browser selection.
    else:
        cbs = unreal.get_editor_subsystem(unreal.ContentBrowserSubsystem)
        sel = cbs.get_selected_paths() or []
        folders = [normalize_cb_folder(str(p)) for p in sel] # Removes the /All/ root if necessary.
    # Gets the folder selected in Content Browser.

    if not folders:
        log("No folder path provided or folders selected.", "warn")
        return []

# Building an asset paths list from all chosen folders:
    assets_pcg_paths: Set[str] = set()

    for folder in folders:
        asset_data_list = registry.get_assets_by_path(
            folder,
            recursive=recursive,
            include_only_on_disk_assets=False,
        )
        for asset_data in asset_data_list:
            pkg = getattr(asset_data, "package_name", None)  # e.g., /Game/.../Asset
            if pkg:
                assets_pcg_paths.add(str(pkg))
    #  Builds a list containing AssetData metadata for each asset in the folder

    return sorted(assets_pcg_paths)


def list_selected_assets() -> List[str]:
 # List assets package paths for assets selected in the Content Browser.
    selected: List[unreal.AssetData] = list(unreal.EditorUtilityLibrary.get_selected_asset_data())

    assets_pkg_paths: Set[str] = set()
    for asset_data in selected:
        pkg: str = getattr(asset_data, "package_name", None)
        if pkg:
            pkg = normalize_cb_folder(str(pkg)) # Removes the /All/ root if necessary.
            if pkg.startswith("/Game/"):
              assets_pkg_paths.add(str(pkg))  # e.g., /Game/.../Asset

    return sorted(assets_pkg_paths)


def match_suffixes(name_lower: str, type_suffix: str, size_suffix: str) -> Optional[str]:
    # Takes into account different naming conventions, returns the regex pattern that matches one.
    # type...size, size...type, ...type

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

    only_type: str = rf"{separator}{re.escape(type_suffix)}$"
    if re.search(only_type, name_lower):
        return only_type
    # Returns this in case only the type suffix is present.
    return None


def normalize_cb_folder(folder: str) -> str:
# Normalizes the package paths.
# Sometimes UE classes return paths as a /All/Game/... instead of the /Game/... e.g., unreal.EditorUtilityLibrary.get_selected_folder_paths()
    path = str(folder)
    if path == "/All":
        return "/"
    if path.startswith("/All/"):
        return path[4:]
    return path


def object_to_package_path(obj_path: str) -> str:
# E.g., Root/A/B/Example.Example > Root/A/B/Example
    if not isinstance(obj_path, str):
        return obj_path

    pkg_path = obj_path.split(":", 1)[0] # If exists, proceeds to delete the subobject from the path

    return pkg_path.split(".", 1)[0]


def package_to_object_path(pkg_path: str) -> str:
    # Assumes the object and package name are the same.
    # E.g., Root/A/B/Example > Root/A/B/Example.Example
    if not isinstance(pkg_path, str):
        unreal.log_error(f"Invalid package path: {pkg_path}")
        return ""
    name: str = pkg_path.rsplit("/", 1)[-1]
    return f"{pkg_path}.{name}"


def resolve_work_dir() -> Tuple[str, bool]:
# Resolves the path for a temporary folder for Unreal or Windows to extract the files to.
# Uses a path provided in config, if no valid path is available, uses the project's default path.

    project_dir: str = unreal.SystemLibrary.get_project_directory()
    default_dir: str = os.path.abspath(os.path.join(project_dir, "TemporaryFolder"))
    cfg = (UNREAL_TEMP_FOLDER or "").strip()

    final_path: str = os.path.abspath(os.path.normpath(cfg)) if cfg else default_dir

    preexisted = os.path.isdir(final_path)
    try:
        os.makedirs(final_path, exist_ok=True)

    except OSError:
        log("No valid path for temp folder; falling back to default.", "warn")
        final_path = default_dir
        preexisted = os.path.isdir(final_path)
        try:
            os.makedirs(final_path, exist_ok=True)
        except OSError:
            log(f"Cannot create default temp folder: {final_path}", "error")
            raise SystemExit(1)
    return final_path, preexisted


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


def validate_export_ext() -> str:
# Validates the selected output extension set in config.

    allowed_ext: set[str] = set(ALLOWED_FILE_TYPES)
    aliases: Dict[str, str] = {"jpeg": "jpg"}

    ext: str = (FILE_TYPE or "").strip().lower().lstrip(".")
    ext = aliases.get(ext, ext)

    if not ext or ext not in allowed_ext:
        log_allowed_ext = ", ".join(sorted(allowed_ext))
        log(f"Invalid file type '{FILE_TYPE}' (allowed: {log_allowed_ext}); falling back to 'png'", "warn")
        ext = "png"
    return ext