
""" Input processing backend: unifies system CLI and Unreal Engine so the main channel_packer logic is platform-agnostic. """
#  It is now split into two separate packages, but still allows the channel_packer function to be used interchangeably between them.

import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import unreal

from ..common_utils import log

from .texture_settings import (AUTO_SAVE, BACKUP_FOLDER_NAME, UNREAL_TEMP_FOLDER, EXR_SRGB_CURVE, DELETE_USED)

from .texture_utils import (ensure_asset_saved, export_temporary_file, get_selected_assets, group_paths_by_folder, is_asset_data, package_to_object_path, validate_export_extension)



@dataclass
class ConvertedEXRImage:
    texture_set_name: Optional[str] = None # Texture set name, added later.
    texture_type: Optional[str] = None # Texture type name.

@dataclass
class CPContext:
    work_directory: str = "" # Absolute path for a temporary folder.
    export_extension: str = "png" # Validated file extension set in config. For now is set to png to simplify json config.
    selection_paths_map: Dict[str, str] = field(default_factory = dict)  # Key is the asset's package path, value is the absolute path of a temporary file when exported to a folder.
    textures_converted_from_raw: Dict[str, ConvertedEXRImage] = field(default_factory = dict) # Collection of temporary converted .exr files for processing in the main module, their texture set name and its texture type.
    temporary_path_already_exist: bool = False # If True, then at the end of the channel_packer the main temp directory isn't deleted not to accidentally delete existing files.
    temporary_subdirectory_paths: Set[str] = field(default_factory = set)  # Set of absolute paths to subfolders created in this run; used for cleanup.




#                                     === Channel Packer core interface ===


def context_validate_export_extension(context: "CPContext" = None) -> None:
# Context wrapper for a regular function.

    if context is None:
        return
    file_extension: str = validate_export_extension() # Legacy now just uses png to simplify the setup.
    context.export_extension = "png"
    return


def list_initial_files(context: "CPContext" = None) -> List[str]:
# Lists package paths of all selected assets of a given type.
# If a folder/folders are selected, they have priority over directly selected assets.

# Finding the paths to all selected assets:
    selected_paths: Set[str] = set()
    package_paths: List[str] = get_selected_assets(recursive = False) or []

    if not package_paths:
        log("No assets selected. Aborting.", "error")
        context.selection_paths_map = {}

    selected_paths.update(package_paths)


 # Filtering selection to contain only Texture assets:
    texture2d_package_paths: List[str] = []
    for package_path in sorted(selected_paths):
        object_path = package_to_object_path(package_path)
        asset_data = unreal.EditorAssetLibrary.find_asset_data(object_path)
        if asset_data and is_asset_data(asset_data, "Texture2D"):
            texture2d_package_paths.append(package_path)

    if not texture2d_package_paths:
        log("No Texture2D selected. Aborting.", "error")
        context.selection_paths_map = {}
        return []


# Saving files paths as dict keys:
    context.selection_paths_map = {package: "" for package in texture2d_package_paths}
    return texture2d_package_paths


def split_by_parent(context: "CPContext") -> Dict[str, List[str]]:
# Groups absolute paths from context.selection_paths values by their parent directory relative to context.work_dir.
# Used to bind together asset in Content Browser, and its exported temporary file on the drive.
# Returns a sorted rel_parent: [file names] map.

    files_absolute_path: List[str] = [path for path in context.selection_paths_map.values() if path]
    root_directory: str = os.path.abspath(context.work_directory)
    grouped_paths_by_parent: Dict[str, List[str]] = defaultdict(list)

    for absolute_path in files_absolute_path:
        if not os.path.isabs(absolute_path):
            absolute_path = os.path.abspath(absolute_path)
        try:
            relative_path = os.path.relpath(absolute_path, root_directory)
        except ValueError:
            continue
        relative_path = relative_path.replace("\\", "/")
        parent_directory_ = os.path.dirname(relative_path)
        parent_path = parent_directory_ if parent_directory_ else "."
        file_name = os.path.basename(relative_path)
        grouped_paths_by_parent[parent_path].append(file_name)

    return {parent_directory: sorted(file_names) for parent_directory, file_names in sorted(grouped_paths_by_parent.items(), key = lambda kv: kv[0])}


def resolve_work_directory(context: "CPContext") -> None:
# Resolves the path for a temporary folder for Unreal or Windows to extract the files to.
# Uses a path provided in config, if no valid path is available, uses the project's default path.

    project_directory: str = unreal.SystemLibrary.get_project_directory()
    default_directory: str = os.path.abspath(os.path.join(project_directory, "TemporaryFolder"))
    temporary_directory = (UNREAL_TEMP_FOLDER or "").strip()

    final_path: str = os.path.abspath(os.path.normpath(temporary_directory)) if temporary_directory else default_directory
    preexisted_directory = os.path.isdir(final_path)
    try:
        os.makedirs(final_path, exist_ok = True)

    except OSError:
        log("No valid path for temp folder; falling back to default.", "warn")
        final_path = default_directory
        preexisted_directory = os.path.isdir(final_path)
        try:
            os.makedirs(final_path, exist_ok = True)
        except OSError:
            log(f"Cannot create default temp folder: {final_path}", "error")
            raise SystemExit(1)


    context.work_directory = final_path
    context.temporary_path_already_exist = preexisted_directory
    return


def prepare_workspace(context: "CPContext") -> None:
# Exports assets whose package paths are keys in context.selection_paths into a temporary folder.
# Writes each absolute exported file path back to context.selection_paths.

# Creating temporary folder and it's subfolders:
    resolve_work_directory(context)
    work_directory: str = context.work_directory


# Preparing the assets:
    saved_asset_only_paths: Dict[str, str] = {}
    for selection_path in list(context.selection_paths_map.keys()):
        if ensure_asset_saved(selection_path, auto_save = AUTO_SAVE):
            saved_asset_only_paths[selection_path] = ""
        else:
            log(f"Skipping unsaved asset: {selection_path}", "warn")
    context.selection_paths_map = saved_asset_only_paths
    # Checks if all selected assets are saved. If specified in the config, saves the unsaved files too.

    paths_grouped_by_parent: Dict[str, List[str]] = group_paths_by_folder(list(context.selection_paths_map.keys()))
    # Groups asset package paths by their parent folder relative to /Game/ folder in Content Browser.

    for parent_folder_path, package_paths in paths_grouped_by_parent.items():
        if parent_folder_path == ".": # For the assets directly in the root folder.
            target_directory: str = work_directory
            subfolder_path: str = None
        else:
            safe_relative_path: str = os.path.normpath(parent_folder_path).lstrip(r"\/")
            target_directory: str = os.path.join(work_directory, safe_relative_path)
            os.makedirs(target_directory, exist_ok = True)
            subfolder_path: str = os.path.abspath(target_directory).replace("\\", "/")
    # Sets the path for a temporary file extraction.


# Exporting assets:
        for package_path in sorted(set(package_paths)):
            asset_name: str = package_path.rsplit("/", 1)[-1]
            object_path: str = package_to_object_path(package_path)
            asset = unreal.EditorAssetLibrary.load_asset(object_path)

            temporary_file: tuple[Optional[str], bool] = export_temporary_file(asset, target_directory, asset_name, package_path, exr_srgb_curve=EXR_SRGB_CURVE)
            temporary_file_path, was_source_float = temporary_file
            if not temporary_file_path:
                continue

            temporary_file_absolute_path: str = os.path.abspath(temporary_file_path).replace("\\", "/")
            context.selection_paths_map[package_path] = temporary_file_absolute_path

            if was_source_float:
                context.textures_converted_from_raw[temporary_file_absolute_path] = ConvertedEXRImage()
            # Stores a converted file path for logs.

            if subfolder_path:
                context.temporary_subdirectory_paths.add(subfolder_path)
            # Adds a path for created sub dirs, used later for cleanup.


def move_used_map(file_path: str, backup_directory: Optional[str], context: "CPContext") -> None:
# Moves asset used for the texture generation to a specified folder.
# Version for Unreal moves assets in Content Browser, so the input backup_directory isn't used.

# Checking the config:
    backup_folder_name: str = (BACKUP_FOLDER_NAME or "").strip().strip("/")
    if not backup_folder_name or DELETE_USED:
        return

# Mapping temporary exported files to the original asset in the Content Browser:
    package_path: str = ""
    input_temporary_file_path: str = os.path.abspath(file_path).replace("\\", "/")
    for context_package_path, temporary_file_path in context.selection_paths_map.items():
        if input_temporary_file_path == temporary_file_path:
            package_path = context_package_path
            break

    if not package_path:
        file_name: str = os.path.basename(input_temporary_file_path)
        log(f"Skipped moving to backup: cannot resolve mapping for {file_name} in the Content Browser.", "error")
        return


# Deriving a mapped asset's final path in Content Browser:
    asset_original_directory = package_path.rsplit("/", 1)[0]
    target_backup_path = f"{asset_original_directory}/{backup_folder_name}"
    # Creates a backup directory path.

    unreal.EditorAssetLibrary.make_directory(target_backup_path)

    asset_name = package_path.rsplit("/", 1)[-1]
    target_asset_path = f"{target_backup_path}/{asset_name}"
    # Creates an asset's final path in a backup directory.

    if unreal.EditorAssetLibrary.does_asset_exist(target_asset_path):
        log(f"Aborted moving to backup: asset already exists at '{target_asset_path}'", "warn")
        return


# Moving the file:
    ok: bool = unreal.EditorAssetLibrary.rename_asset(package_path, target_asset_path)
    if not ok:
        log(f"Content Browser asset move failed: '{package_path}' to '{target_asset_path}'", "warn")


def cleanup(context: "CPContext") -> None:
# Removes temporary files and their subfolders.
# Deletes assets used in creating the packaged texture if specified.

    work_directory: str = context.work_directory.strip()

# Deleting extracted files:
    selection_paths: Dict[str, str] = context.selection_paths_map or {}
    work_directory_absolute: str = os.path.abspath(os.path.normpath(context.work_directory)).replace("\\", "/")
    for context_temporary_file_path in selection_paths.values():
        if not context_temporary_file_path:
            continue
        temporary_file_path: str = os.path.abspath(os.path.normpath(context_temporary_file_path)).replace("\\", "/")
        if temporary_file_path.startswith(work_directory_absolute) and os.path.isfile(temporary_file_path):
            try:
                os.remove(temporary_file_path)
            except FileNotFoundError:
                pass
            except PermissionError as error:
                log(f"No permission to remove '{temporary_file_path}': {error}", "warn")
            except OSError as error:
                log(f"Failed to remove '{temporary_file_path}': {error}", "warn")


# Delete used files:
    if DELETE_USED:
        for package_path in (context.selection_paths_map or {}):
            if not package_path.startswith("/Game/"):
                continue

            if unreal.EditorAssetLibrary.does_asset_exist(package_path):
                ok: bool = unreal.EditorAssetLibrary.delete_asset(package_path)
                if not ok:
                    log(f"Failed to delete asset '{package_path}' from Content Browser.", "warn")


# Deleting Empty folders:
    project_root_directory: str = os.path.abspath(unreal.SystemLibrary.get_project_directory())
    content_root_directory: str = os.path.abspath(unreal.SystemLibrary.get_project_content_directory())
    is_critical_directory: bool = work_directory in {project_root_directory, content_root_directory}
    # Extra safety check to never delete the Project or Content root directories.

    if not context.temporary_path_already_exist and not is_critical_directory:
        shutil.rmtree(work_directory, ignore_errors = True)
        return
    elif not context.temporary_path_already_exist and is_critical_directory:
        log(f"Critical folder used as temporary directory: {work_directory}. Cleaning subfolders only.", "error")

    for temporary_subdirectories in sorted(context.temporary_subdirectory_paths, key = lambda p: p.count(os.sep)):
        if os.path.commonpath([work_directory, temporary_subdirectories]) != work_directory:
            continue

        for root, _, _ in os.walk(temporary_subdirectories, topdown = False):
            try:
                os.rmdir(root)
            except OSError:
                pass
    # Removes only empty directories under each created subdir.
