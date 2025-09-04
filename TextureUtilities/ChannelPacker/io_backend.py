
""" Input processing backend: unifies system CLI and Unreal Engine so the main channel_packer logic is platform-agnostic. """
#  It is now split into two separate packages, but still allows the channel_packer function to be used interchangeably between them.

import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import unreal

from ..image_lib import ImageObj, save_image as save_image_file

from ..texture_settings import (AUTO_SAVE, BACKUP_FOLDER_NAME, DELETE_USED)

from ..texture_utils import (ensure_asset_saved, get_selected_assets, get_tex_compression_settings,
    group_paths_by_folder, is_asset_data, log, package_to_object_path, resolve_work_dir, validate_export_ext)

from .settings import (PACKING_MODES)


@dataclass
class CPContext:
    work_dir: str = "" # Absolute path for a temporary folder.
    selection_paths: Dict[str, str] = field(default_factory=dict)  # Key is the asset's package path, value is the absolute path of a file when exported to a temporary folder
    export_ext: str = "" # Validated file extension set in config.
    modes_compression_type: Dict[str, Tuple[unreal.TextureCompressionSettings, bool]] = field(default_factory=dict) # Compression setting for imported packed textures for each mode.
    temp_path_already_exist: bool = False # If True, then at the end of the channel_packer the main temp directory isn't deleted not to accidentally delete existing files.
    created_sub_dirs: Set[str] = field(default_factory=set)  # Set of absolute paths to subfolders created in this run; used for cleanup.




#                                     === Channel Packer core interface ===


def validate_export_ext_ctx(ctx: "CPContext" = None) -> None:
    # ctx wrapper for a regular function.

    ext = validate_export_ext()
    ctx.export_ext = ext
    return


def split_by_parent(ctx: "CPContext") -> Dict[str, List[str]]:
# Groups absolute paths from ctx.selection_paths values by their parent directory relative to ctx.work_dir.
# Used to bind together asset in Content Browser, and it's exported temporary file on the drive.
# Returns a sorted rel_parent: [file names] map.

    files_abs: List[str] = [v for v in ctx.selection_paths.values() if v]
    root: str = os.path.abspath(ctx.work_dir)
    groups: Dict[str, List[str]] = defaultdict(list)

    for ap in files_abs:
        if not os.path.isabs(ap):
            ap = os.path.abspath(ap)
        try:
            rel = os.path.relpath(ap, root)
        except Exception:
            continue
        rel = rel.replace("\\", "/")
        parent = os.path.dirname(rel)
        key = parent if parent else "."
        name = os.path.basename(rel)
        groups[key].append(name)

    return {k: sorted(v) for k, v in sorted(groups.items(), key=lambda kv: kv[0])}


def list_initial_files(input_folder: str, ctx: "CPContext", ) -> List[str]:
# Lists package paths of all selected assets of a given type.
# If a folder/folders are selected, they have priority over directly selected assets.
# Input folder is used only with Windows backend. Left for compatibility of the main channel_packer.


# Finding the paths to all selected assets:
    collected: Set[str] = set()
    pkgs: List[str] = get_selected_assets(recursive=False) or []

    if not pkgs:
        log("No assets selected. Aborting.", "error")
        ctx.selection_paths = {}

    collected.update(pkgs)


 # Filtering selection to contain only Texture assets:
    texture_pkgs: List[str] = []
    for pkg_path in sorted(collected):
        obj_path = package_to_object_path(pkg_path)
        asset_data = unreal.EditorAssetLibrary.find_asset_data(obj_path)
        if asset_data and is_asset_data(asset_data, "Texture2D"):
            texture_pkgs.append(pkg_path)

    if not texture_pkgs:
        log("No Texture2D selected. Aborting.", "error")
        ctx.selection_paths = {}
        return []

# Saving files paths as dict keys:
    ctx.selection_paths = {pkg: "" for pkg in texture_pkgs}
    return texture_pkgs


def prepare_workspace(_unused: List[str], ctx: "CPContext") -> None:
# Exports assets whose package paths are keys in ctx.selection_paths into a temporary folder.
# Writes each absolute exported file path back to ctx.selection_paths.

# Setting Texture Compression Settings per mode:
    packing_mode_compression_map(ctx)

# Creating temporary folder and it's subfolders:
    resolve_work_dir_ctx(ctx)
    work_dir = ctx.work_dir


# Ensuring all assets are saved before beginning working on them:
    cleaned: Dict[str, str] = {}
    for pkg in list(ctx.selection_paths.keys()):
        if ensure_asset_saved(pkg, auto_save=AUTO_SAVE):
            cleaned[pkg] = ""
        else:
            log(f"Skipping unsaved asset: {pkg}", "warn")
    ctx.selection_paths = cleaned


    # Checks if all selected assets are saved. If specified in the config, saves the unsaved files too.


    groups: Dict[str, List[str]] = group_paths_by_folder(list(ctx.selection_paths.keys()))
    # Groups asset package paths by their parent folder relative to /Game/ folder in Content Browser.

    for parent_folder, pkg_paths in groups.items():
        if parent_folder == ".": # For the assets directly in the root folder.
            out_dir = work_dir
            sub_folder_path: str = None
        else:
            safe_rel = os.path.normpath(parent_folder).lstrip(r"\/")
            out_dir = os.path.join(work_dir, safe_rel)
            os.makedirs(out_dir, exist_ok=True)
            sub_folder_path = os.path.abspath(out_dir).replace("\\", "/")


# Exporting assets:
        for pkg_path in sorted(set(pkg_paths)):
            asset_name: str = pkg_path.rsplit("/", 1)[-1]
            object_path: str  = package_to_object_path(pkg_path)
            asset: unreal.Object = unreal.EditorAssetLibrary.load_asset(object_path)

            ext = ctx.export_ext or "png"
            final_path: str = os.path.join(out_dir, f"{asset_name}.{ext}")

            task = unreal.AssetExportTask()
            task.object = asset
            task.filename = final_path
            task.automated = True
            task.prompt = False
            task.replace_identical = True


# Stores the absolute export path ase a value for each asset's key in ctx.selection_paths
            ok = unreal.Exporter.run_asset_export_task(task)
            if ok:
                abs_path = os.path.abspath(final_path).replace("\\", "/")
                ctx.selection_paths[pkg_path] = abs_path
                if sub_folder_path:
                    ctx.created_sub_dirs.add(sub_folder_path) # Used by the cleanup_temp_folders to delete each subfolder
            else:
                log("Error while exporting files to a temporary folder", "error")


def save_image(img: ImageObj, out_dir: str, filename: str, mode_name: str | None, ctx: "CPContext") -> None:
# Writes image to a temp file in out_dir, then imports it into the Content Browser to a corresponding folder with proper texture compression setting.
# Deletes the temp file afterward.
# Returns the imported asset's package path.


# Creating final paths in Content Browser:
    work_dir = ctx.work_dir
    relative_path = os.path.relpath(out_dir, work_dir).replace("\\", "/")
    if relative_path in (".", ""):
        dest_pkg_dir = "/Game"
    else:
        dest_pkg_dir = f"/Game/{relative_path.lstrip('/').lstrip('./')}"


# Writing a temporary file into out_dir:
    ext = ctx.export_ext
    os.makedirs(out_dir, exist_ok=True)
    tmp_file = os.path.join(out_dir, f"{filename}.{ext}")
    try:
        save_image_file(img, tmp_file) # Saves the file using an image library.


# Importing the file into Unreal Engine:
        unreal.EditorAssetLibrary.make_directory(dest_pkg_dir)

        task = unreal.AssetImportTask()
        task.filename = tmp_file
        task.destination_path = dest_pkg_dir
        task.destination_name = filename
        task.automated = True
        task.replace_existing = True

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])


        dest_asset = f"{dest_pkg_dir}/{filename}"
        imported_paths = list(task.imported_object_paths or [])

        if not imported_paths or not unreal.EditorAssetLibrary.does_asset_exist(dest_asset):
            log(f"Couldn't import created map into Unreal: '{dest_asset}'. Aborting.", "error")
            raise SystemExit(1)


# Setting proper compression type per mode:
        tex = unreal.EditorAssetLibrary.load_asset(dest_asset)
        if tex:
            compression_type, srgb = ctx.modes_compression_type.get(
                (mode_name or "").strip().lower(),
                (unreal.TextureCompressionSettings.TC_DEFAULT, True)  # fallback
            )

            if tex.get_editor_property("compression_settings") != compression_type:
                tex.set_editor_property("compression_settings", compression_type)

            if tex.get_editor_property("sRGB") != srgb:
                tex.set_editor_property("sRGB", srgb)


            if AUTO_SAVE:
                unreal.EditorAssetLibrary.save_loaded_asset(tex, only_if_is_dirty=True)


# Deleting a temporary file:
    finally:
        try:
            if os.path.isfile(tmp_file):
                os.remove(tmp_file)
        except Exception:
            pass


def move_used_map(file_path: str, bak_dir: Optional[str], ctx: "CPContext") -> None:
# Moves asset used for the texture generation to a specified folder.
# Version for Unreal moves assets in Content Browser, so input bak_dir isn't used.



# Checking the config:
    bak: str = (BACKUP_FOLDER_NAME or "").strip().strip("/")
    if not bak or DELETE_USED:
        return

# Mapping temporary exported files to the original asset in the Content Browser:
    pkg_path: str = ""
    file_path_norm: str = os.path.abspath(file_path).replace("\\", "/")
    for pkg, abs_path in ctx.selection_paths.items():
        if file_path_norm == abs_path:
            pkg_path = pkg
            break

    if not pkg_path:
        file_name: str = os.path.basename(file_path_norm)
        log(f"Skip moving to backup: cannot resolve mapping for {file_name} in the Content Browser.", "error")
        return


# Deriving a mapped asset's final path in Content Browser:
    base_dir = pkg_path.rsplit("/", 1)[0]
    dest_dir = f"{base_dir}/{bak}"
    # Creates a backup directory path.

    unreal.EditorAssetLibrary.make_directory(dest_dir)

    base_name = pkg_path.rsplit("/", 1)[-1]
    dest_asset = f"{dest_dir}/{base_name}"
    # Creates an asset's final path in a backup directory.

    if unreal.EditorAssetLibrary.does_asset_exist(dest_asset):
        log(f"Aborted moving to backup: asset already exists at '{dest_asset}'", "warn")
        return


# Moving the file:
    ok = unreal.EditorAssetLibrary.rename_asset(pkg_path, dest_asset)
    if not ok:
        log(f"CB move failed: '{pkg_path}' → '{dest_asset}'", "warn")


def cleanup(ctx: "CPContext") -> None:
    work_dir: str = ctx.work_dir.strip()

# Deleting extracted files:
    sel_paths = ctx.selection_paths or {}
    work_dir_c = os.path.abspath(os.path.normpath(ctx.work_dir)).replace("\\", "/")
    for p in sel_paths.values():
        if not p:
            continue
        ap = os.path.abspath(os.path.normpath(p)).replace("\\", "/")
        if ap.startswith(work_dir_c) and os.path.isfile(ap):
            try:
                os.remove(ap)
            except FileNotFoundError:
                pass
            except PermissionError as e:
                log(f"No permission to remove '{ap}': {e}", "warn")
            except OSError as e:
                log(f"Failed to remove '{ap}': {e}", "warn")


# Delete used files:
    if DELETE_USED:
        for pkg_path in (ctx.selection_paths or {}):
            if not pkg_path.startswith("/Game/"):
                continue

            if unreal.EditorAssetLibrary.does_asset_exist(pkg_path):
                ok = unreal.EditorAssetLibrary.delete_asset(pkg_path)
                if not ok:
                    log(f"Failed to delete asset '{pkg_path}' from Content Browser.", "warn")


# Deleting Empty folders:
    project_root: str = os.path.abspath(unreal.SystemLibrary.get_project_directory())
    content_root: str = os.path.abspath(unreal.SystemLibrary.get_project_content_directory())
    is_critical_root: bool = work_dir in {project_root, content_root}
    # Extra safety check to never delete the Project or Content root directories.

    if not ctx.temp_path_already_exist and not is_critical_root:
        shutil.rmtree(work_dir, ignore_errors=True)
        return
    elif not ctx.temp_path_already_exist and is_critical_root:
        log(f"Critical folder used as temporary directory: {work_dir}. Cleaning subfolders only.", "error")

    for base in sorted(ctx.created_sub_dirs, key=lambda p: p.count(os.sep)):
        if os.path.commonpath([work_dir, base]) != work_dir:
            continue

        for root, _, _ in os.walk(base, topdown=False):
            try:
                os.rmdir(root)
            except OSError:
                pass
    # Removes only empty directories under each created subdir.




#                                       === Unreal backend only ===


def resolve_work_dir_ctx(ctx: "CPContext") -> None:
# ctx wrapper for a regular function.
# Resolves the path for a temporary folder for Unreal to extract the files to.
# Uses a path provided in config, if no valid path is available, uses the project's default path.

    final_path, preexisted = resolve_work_dir()
    ctx.work_dir = final_path
    ctx.temp_path_already_exist = preexisted
    return None


def packing_mode_compression_map(ctx: "CPContext") -> None:
    packing_modes = PACKING_MODES
    compression_map: Dict[str, Tuple[unreal.TextureCompressionSettings, bool]] = {}
    for mode in packing_modes:
        name = (mode.get("mode_name") or "").strip()
        tex_comp = mode.get("texture_compression")

        compression_type, default_srgb, valid_comp_setting = get_tex_compression_settings(
            mode.get("texture_compression")
        )

        override = mode.get("sRGB")
        if isinstance(override, bool): # Input: True/False bool.
            srgb = override

        elif isinstance(override, str) and override.strip() != "": # Input: Literal "sRGB/RGB".
            val = override.strip().lower()
            if val == "srgb":
                srgb = True
            elif val == "rgb":
                srgb = False
            else:
                srgb = default_srgb
        else:
            srgb = default_srgb
        # Overrides the default sRGB mode with the user-set config.
        compression_map[name.lower()] = (compression_type, srgb)


        if not valid_comp_setting and name != "":
            if tex_comp:
                log(f"Mode '{name}': Unknown texture_compression '{tex_comp}'. Using TC_DEFAULT.", "warn")
            else:
                log(f"Mode '{name}': Empty texture_compression. Using TC_DEFAULT.", "warn")

    ctx.modes_compression_type = compression_map
    return