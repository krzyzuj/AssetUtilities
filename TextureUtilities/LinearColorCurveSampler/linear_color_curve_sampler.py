
""" Creates Linear Color Curve Asset with colors sampled from the selected texture. """

import os
import unreal
import csv
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


from ...common_utils import (clear_source_file_for_asset, log, validate_safe_folder_name)

from ..image_lib import (get_size, ImageObject, linear_01_to_srgb, new_image, open_image, paste, resize_nearest, save_image, srgb_image_to_linear_channels_01, srgb_to_linear01)

from ..texture_settings import (CUSTOM_PREFIX, COLORCURVE_TARGET_FOLDER_NAME as TARGET_FOLDER_NAME, SWATCH_COUNT, EXPORT_PRESET, DIVISION_METHOD, LIGHT_BAND_SIZE, STEP_TRANSITION, USE_FULL_RESOLUTION, CREATE_CURVE_ATLAS, CUSTOM_CURVE_ATLAS_PREFIX, BACKUP_FOLDER_NAME, DEBUG)

from ..texture_io_backend import (cleanup, CPContext, list_initial_files, move_used_map, prepare_workspace, split_by_parent,)

from ..texture_utils import (derive_texture_name, make_output_dirs)

from .presets import (iter_presets, PresetConfig, PresetName)

from .classes import (HueModeType, HueWeightType, LightnessWeightType, SwatchResult)


ALPHA_THRESHOLD: int = 64 # 0-256 Ignores pixels with less/equal Alpha value.
SWATCH_SIZE: int = 100 # pixels
DOWNSCALE_SIZE: int = 256 # pixels
CHROMA_GRAY_THRESHOLD: float = 0.055 # OKLCh chroma threshold for the pixels to be considered gray, their influence on the resulting color is minimized, and more accurate colors end up in the swatches, 0.055 seems to be the best value.
MIN_PERCEPTUAL_LIGHTNESS_TARGET_SPACING_FACTOR: float = 2.0 # Perceptual segment method only | factor for the minimum separation between adjacent target quantiles.




#                                           === Pipeline ===


def linear_color_curve_sampler():
    context = CPContext()
    preset = EXPORT_PRESET
    context.export_extension = "png"

    log(f"Linear Color Curves Sampler started.", "info")
    # Prints info.

# Preparing the files:
    try:
        validate_safe_folder_name(BACKUP_FOLDER_NAME)
        validate_safe_folder_name(TARGET_FOLDER_NAME)
        # Checks if folder names don't contain unsupported characters.

        selected_assets = list_initial_files(context) # Lists selected Texture2D assets in the Content Browser.
        if not selected_assets:
            return
        prepare_workspace(context) # Sets a final work directory path and extracts assets to the temporary folders.

        grouped_files: Dict[str, List[str]] = split_by_parent(context) # Groups absolute file paths by their parent folder, used later to export all grouped files into the same target folder in Unreal. Returns "." if the file directory is the same as root directory.
        work_directory: str = os.path.abspath(context.work_directory)

        for parent_folder_path, file_names in grouped_files.items():
            final_folder_path: str = os.path.abspath(os.path.join(work_directory, "." if parent_folder_path == "." else parent_folder_path))

            target_directory, backup_directory = make_output_dirs(
                final_folder_path,
                target_folder_name = TARGET_FOLDER_NAME,
                backup_folder_name = BACKUP_FOLDER_NAME
            )
            # Derives final target/backup directories for the temporary files for each path's group.

            relative_path: str = os.path.relpath(target_directory, work_directory).replace("\\", "/")
            target_folder_package_path: str = "/Game" if relative_path in (".", "") else f"/Game/{relative_path.lstrip('/').lstrip('./')}"
            # Sets a final target folder path for the group in Content Browser.


# Processing the files and creating samples:
            for file_name in file_names:
                target_file_absolute_path: str = os.path.join(final_folder_path, file_name)
                asset_name: str = derive_texture_name(Path(file_name).stem) # Deriving name from the grouped paths, since this Dicts contains file paths only.

                created_previews: list[str] = [] # DEBUG
                imported_assets: list[str] = [] # DEBUG
                for preset_name, config in iter_presets(preset):
                    results: List[SwatchResult] = sample_texture_colors(target_file_absolute_path, preset = config)

                    assets = export_swatches_csv(
                        results = results,
                        preset = preset_name,
                        asset_name = asset_name,
                        target_temporary_file_path = target_directory,
                        target_content_browser_path = target_folder_package_path
                    )
                    imported_assets.append(assets)

                    if DEBUG:
                        previews = create_swatch_previews(
                            results = results,
                            preset = preset_name,
                            asset_name = asset_name,
                            target_temporary_file_path = target_directory,
                            target_content_browser_path = target_folder_package_path
                        )
                        created_previews.append(previews)
                # Processing each set preset for the current file.

                if CREATE_CURVE_ATLAS:
                    curve_paths = [asset_path for asset_path in imported_assets if asset_path]

                    atlas_path = create_or_update_curve_atlas(
                        curve_asset_name=asset_name,
                        curve_package_paths=curve_paths,
                        target_content_browser_path=target_folder_package_path
                    )
                    if not atlas_path:
                        log(f"[linear Color Curve Sampler] Unable to create/update curve atlas for: '{asset_name}'",
                            "error")
                # Creates a Curve Atlas and plugs generated curves to their coressponding atlases.

                move_used_map(target_file_absolute_path, backup_directory, context) # Moves the source map into the backup directory only when BACKUP_FOLDER_NAME is set in the config.

            if DEBUG:
                log("[linear Color Curve Sampler] Successfully imported:\n" + "\n".join(f"  - {name}" for name in created_previews),"info")
                log("[linear Color Curve Sampler] Successfully imported:\n" + "\n".join(f"  - {name}" for name in imported_assets),"info")
                # Prints info.


# Deleting temporary extracted files:
    finally:
        if not DEBUG:
            cleanup(context)
        log(f"Successfully generated color curves", "info")
        # Prints info.


def sample_texture_colors(input_path, preset: [PresetConfig | PresetName]) -> List[dict]:
# Derives n representative color samples from the texture.
# First divides available lightness range by the number of the final swatches. Then for each lightness target calculates the lightness weight for each pixel.
# In "diverse", and "dominant" hue modes it additionally puts each pixel that contributes weight for the current lightness target into to the bin closest to its hue degree value and weights it.
# Hue associated with the bin with the highest value gets selected to make sure that in those modes different/dominant hues are chosen for the swatch on top of their selected lightness value.

    swatches_amount: float = SWATCH_COUNT
    input_alpha_threshold: float = ALPHA_THRESHOLD
    use_full_resolution: bool = USE_FULL_RESOLUTION
    normalised_light_band_size: float = 0.0001 + (0.05 - 0.0001) * max(0.0, min(1.0, LIGHT_BAND_SIZE))  # Maps recommended values of 0.0001-0.05 into the more manageable 0-1 range.

    config = preset
    lightness_weight_method = config.LIGHTNESS_WEIGHT_METHOD
    hue_mode = config.HUE_MODE
    hue_weight_method = config.HUE_WEIGHT_METHOD
    hue_band_size = config.HUE_BAND_SIZE

# Preparing the image:
    image_srgb: ImageObject = open_image(input_path)

    if not use_full_resolution:
        width, height = get_size(image_srgb)
        long_side: int = max(width, height)
        if long_side > DOWNSCALE_SIZE:
            scale: float = DOWNSCALE_SIZE / long_side
            image_new_size = (int(round(width * scale)), int(round(height * scale)))
            image_srgb = resize_nearest(image_srgb, image_new_size)


    r_linear, g_linear, b_linear, alpha = srgb_image_to_linear_channels_01(image_srgb)


    # Storing channels as lists:
    r_linear_values: List[float] = list(r_linear.getdata())
    g_linear_values: List[float]  = r_linear_values if g_linear is r_linear else list(g_linear.getdata())
    b_linear_values: List[float]  = r_linear_values if b_linear is r_linear else list(b_linear.getdata())
    # If the image is grayscale, then green and blue channels are just aliases to the red channel, instead of making separate lists.

    if alpha is None:
        alpha_values: List[float] = [1.0] * len(r_linear_values)
        # If alpha is missing, creates a list that has 1.0 for every pixel so its content matches the other channels.
    else:
        alpha_values: List[float] = list(alpha.getdata())

    # Collecting only the indices of pixels with alpha above a given threshold:
    alpha_threshold = (input_alpha_threshold / 255.0)
    opaque_pixels_indices = [pixel for pixel in range(len(r_linear_values)) if alpha_values[pixel] > alpha_threshold]
    if not opaque_pixels_indices:
        raise ValueError("No pixels passed the alpha filter.")

    alpha_weights: List[float] = [alpha_values[index] for index in opaque_pixels_indices] # Alpha weight to scale semi-transparent pixels influences on the final swatch.


# Converting data to OKLCh:
    h_oklch_list: List[float] = [] # OKLCh: hue h [°]
    c_oklch_list: List[float] = [] # OKLCh: chroma C
    l_list: List[float] = [] # OKLab/OKLCh Lightness 0-1

    for pixel in opaque_pixels_indices:
        r, g, b = r_linear_values[pixel], g_linear_values[pixel], b_linear_values[pixel]  # 0-1 range
        l_oklab, a_oklab, b_oklab = _rgb_linear_01_to_oklab(r, g, b)
        _, c_oklch, h_oklch = _oklab_to_oklch(l_oklab, a_oklab, b_oklab)
        h_oklch_list.append(h_oklch) # [°]
        c_oklch_list.append(c_oklch)
        l_list.append(l_oklab) # 0-1 range


# Deriving present lightness values and normalizing them to 0-1 range:
    l_min = min(l_list)
    l_max = max(l_list)

    if l_list and (l_max - l_min) > 0:
        scale_to_01_range: float = 1.0 / (l_max - l_min) # Maps l_min and l_max to 0-1 range.
        lightness_list = [(l_value - l_min) * scale_to_01_range for l_value in l_list] # In 0-1 range.
    else:
        lightness_list = [0.5] * len(l_list)
        # For the edge case when all the pixels have the same lightness value.


# Calculating lightness targets for each swatch:
    lightness_targets = _calculate_lightness_targets(lightness_list, normalised_light_band_size)

# Calculating the swatches:
    swatches: List[dict] = [] # Final color swatches.
    collected_hue_targets: List[float] = []  # Used in "diverse" mode: stores previous hue targets [°] to repel the current hue target.
    valid_pixels: int = len(opaque_pixels_indices) # Total number of the pixels that passed Alpha check.

    for index, lightness_target in enumerate(lightness_targets):

        lightness_weights = [_calculate_lightness_weight(abs(lightness_list[pixel] - lightness_target), normalised_light_band_size, lightness_weight_method) for pixel in range(valid_pixels)]
        lightness_weights_alpha: List[float] = [lightness_weight * alpha_weights[pixel] for pixel, lightness_weight in enumerate(lightness_weights)] # Alpha weight to scale semi-transparent pixels influences on the final swatch.
        contributing_pixels: List[int] = [pixel for pixel, weight in enumerate(lightness_weights_alpha) if weight > 0] # Indices of pixels contributing to the current lightness_target only.
        #  Calculates lightness weights.

        hue_weights: List[float]
        hue_target: Optional[float] # Used for debugging only in the main function.

        hue_weights, hue_target = _calculate_hue_weights(
            lightness_weights_alpha,
            contributing_pixels,
            c_oklch_list,
            h_oklch_list,
            hue_mode = hue_mode,
            hue_weight_method = hue_weight_method,
            hue_band_size = hue_band_size,
            collected_hue_targets = collected_hue_targets,
        )
        # Calculates hue weights, 1.0 when non "diverse" or "dominant" hue mode.


        weight_sum: float = 0.0
        r_sum:float = 0
        g_sum: float = 0
        b_sum: float = 0.0
        contributing_pixels_count: int = 0 # Debug
        contributing_pixels_above_gray_threshold: int = 0 # Debug

        for pixel, hue_weight in zip(contributing_pixels, hue_weights):
            final_pixel_weight = lightness_weights_alpha[pixel] * hue_weight
            if final_pixel_weight <= 0.0:
                continue

            opaque_pixel: int = opaque_pixels_indices[pixel]
            weight_sum += final_pixel_weight
            r_sum += final_pixel_weight * r_linear_values[opaque_pixel]
            g_sum += final_pixel_weight * g_linear_values[opaque_pixel]
            b_sum += final_pixel_weight * b_linear_values[opaque_pixel]

            contributing_pixels_count += 1
            if c_oklch_list[pixel] >= CHROMA_GRAY_THRESHOLD: contributing_pixels_above_gray_threshold += 1
        # Calculates final resulting weight for each channel.

        r_mean: float = r_sum / weight_sum
        g_mean: float = g_sum / weight_sum
        b_mean: float = b_sum / weight_sum
        rgb_mean: tuple[float, float, float] = (linear_01_to_srgb(r_mean), linear_01_to_srgb(g_mean), linear_01_to_srgb(b_mean))
        # Calculating final swatch color.


        swatches.append(dict(
            rank = (0.0 if swatches_amount == 1 else index / (swatches_amount - 1)),
            target_L = float(lightness_target),
            picked_color = rgb_mean,
            pixels_used = contributing_pixels_count, # Debug
            pixel_used_above_gray_threshold = contributing_pixels_above_gray_threshold, # Debug
            hue_target = hue_target # Debug
        ))
        # Swatch generation.


# Debug logs:
    if DEBUG:
        log("", "info")
        log("", "info")
        log("", "info")
        # Prints separation.
        if hue_mode != "diverse":
            log("DEBUG: L target | contributing pixels:", "info")
            # Prints info.
            for i, s in enumerate(swatches, 1):
                L = s.get("target_L", None)
                L_str = f"{L:.3f}" if isinstance(L, (int, float)) else "—"
                pixels = s.get("pixels_used", 0)
                log(f"swatch{i:02d}: L={L_str} | {pixels:5d}", "info")
                # Prints info.
        else:
            log("DEBUG: L target | contributing pixels | pixels above gray threshold | hue_target:", "info")
            # Prints info.
            for i, s in enumerate(swatches, 1):
                L = s.get("target_L", None)
                L_str = f"{L:.3f}" if isinstance(L, (int, float)) else "—"
                pixels = s.get("pixels_used", 0)
                gray = s.get("pixel_used_above_gray_threshold", 0)
                hue = s.get("hue_target", None)
                hue_str = f"{hue:.1f}°" if isinstance(hue, (int, float)) else "—"
                log(f"swatch{i:02d}: L={L_str} | {pixels:5d} | {gray:5d} | {hue_str:>7}", "info")
                # Prints info.
        log("", "info")
        # Prints separation.
    return swatches




#                                           === I/O ===

def export_swatches_csv(*, results: Sequence[SwatchResult], preset: PresetName, asset_name: str, target_temporary_file_path: str, target_content_browser_path: str) -> Optional[str]:
# Generates a temporary CSV file with input curve keys (Time, R, G, B, A).
# Assigns asset type prefix "CC" (by default).
# Creates the UCurveLinearColor from the CSV and cleans up the temporary CSV.
# Returns the created asset path for debug.

#  Preparing the data:
    target_temporary_file_path: str = os.path.abspath(target_temporary_file_path)
    export_prefix: str = CUSTOM_PREFIX if CUSTOM_PREFIX else "CC"
    swatch_count: int = len(results)
    exporting_multiple: bool = (EXPORT_PRESET == "all")
    current_preset_name: str = str(preset).lower()

    if exporting_multiple:
        csv_file_name: str = f"{export_prefix}_{asset_name}_{current_preset_name}"
    else:
        csv_file_name: str = f"{export_prefix}_{asset_name}"

    csv_path: str = os.path.join(target_temporary_file_path, f"{csv_file_name}.csv")
    curve_package_path: str = f"{target_content_browser_path}/{csv_file_name}"


# Generating the CSV file:
    rows: list[list[float]] = [] # Rows of CSV file.

    if not STEP_TRANSITION:
        for index, swatch in enumerate(results):
            if swatch_count > 1:
                time = index / (swatch_count - 1) # 0-1 time range divide equally for the swatches.
            else:
                time = 0.0

            r8, g8, b8 = swatch["picked_color"]
            r_lin: float = srgb_to_linear01(r8)
            g_lin: float = srgb_to_linear01(g8)
            b_lin: float = srgb_to_linear01(b8)
            a_lin: float = 1.0
            # Converts sRGB to linear rgb for accurate colors.

            rows.append([time, r_lin, g_lin, b_lin, a_lin]) # CSV format for Unreal: Time, R, G, B, where Time is the placement on the 0-1 curve.
    # "Regular" smooth interpolations between swatches

    else:
        for index, swatch in enumerate(results):
            if swatch_count > 1:
                time = index / swatch_count  # Creates on more "sample" that given swatches, so the last swatch covers the same space in 0-1 as other swatches instead of being only at 1.
            else:
                time = 0.0

            r8, g8, b8 = swatch["picked_color"]
            r_lin: float = srgb_to_linear01(r8)
            g_lin: float = srgb_to_linear01(g8)
            b_lin: float = srgb_to_linear01(b8)
            a_lin: float = 1.0
            # Converts sRGB to linear rgb for accurate colors.

            if index > 0 and swatch_count > 1:
                previous_swatch_time: float = (index - 1) / swatch_count
                step_gap: float = max(0.0, time - previous_swatch_time)
                epsilon: float = max(0.001, min(0.01, 0.25 * step_gap))
                time_before: float = max(0.0, time - epsilon)

                prev_r8, prev_g8, prev_b8 = results[index - 1]["picked_color"]
                prev_r_lin: float = srgb_to_linear01(prev_r8)
                prev_g_lin: float = srgb_to_linear01(prev_g8)
                prev_b_lin: float = srgb_to_linear01(prev_b8)

                if time_before <= previous_swatch_time:
                    time_before = (previous_swatch_time + time) * 0.5 if time > previous_swatch_time else previous_swatch_time + 1e-6
                rows.append([time_before, prev_r_lin, prev_g_lin, prev_b_lin, a_lin])
            # Adds a point just before each swatch (except the first) with the previous swatch's color to hold the previous color until the new key.
            rows.append([time, r_lin, g_lin, b_lin,a_lin]) # CSV format for Unreal: Time, R, G, B, where Time is the placement on the 0-1 curve.

        if swatch_count >= 1:
            last_r8, last_g8, last_b8 = results[-1]["picked_color"]
            last_r_lin = srgb_to_linear01(last_r8)
            last_g_lin = srgb_to_linear01(last_g8)
            last_b_lin = srgb_to_linear01(last_b8)
            rows.append([1.0, last_r_lin, last_g_lin, last_b_lin, 1.0])
            # Pastes the same RGB values of the last swatch to the "extra" last sample, so the last swatch covers the same space in 0-1 as other swatches instead of being only at 1.
    # Mimics step transitions, instead of smooth interpolation.


# Saving the temporary CSV file:
    try:
        os.makedirs(os.path.dirname(csv_path), exist_ok = True)
        with open(csv_path, "w", encoding = "utf-8", newline = "") as file:
            w = csv.writer(file)
            for row in rows:
                w.writerow(row)
    except Exception as e:
        log(f"[CSV Export] Failed to write '{csv_path}': {e}", "error")
        return None


# Importing to Unreal:
    try:
        unreal.EditorAssetLibrary.make_directory(target_content_browser_path)

        task = unreal.AssetImportTask()
        task.filename = csv_path
        task.destination_path = target_content_browser_path
        task.destination_name = csv_file_name
        task.replace_existing = True
        task.automated = True
        task.save = True

        factory = unreal.CSVImportFactory()
        settings = unreal.CSVImportSettings()
        settings.import_type = unreal.CSVImportType.ECSV_CURVE_LINEAR_COLOR
        factory.automated_import_settings = settings
        task.factory = factory

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        if not unreal.EditorAssetLibrary.does_asset_exist(curve_package_path):
            log(f"[Export Swatches CSV] Import failed: '{curve_package_path}'", "error")
            return None

        curve_object_path: str = f"{curve_package_path}.{csv_file_name}"
        curve_asset: Optional[unreal.Object] = unreal.EditorAssetLibrary.load_asset(curve_object_path)
        if not curve_asset:
            log(f"[Export Swatches CSV] Failed to load imported asset: '{curve_object_path}'", "error")
            return None

        source_file_cleared: bool = clear_source_file_for_asset(curve_asset)
        if not source_file_cleared:
            log(f"[Export Swatches CSV] clear_source_file_for_asset(): nothing changed for '{curve_object_path}'", "warning")
        # Clearing the path to the Source File in Curve's details.


    # Deleting generated temporary files:
    finally:
        try:
            if os.path.isfile(csv_path):
                os.remove(csv_path)
        except Exception as e:
            log(f"[Export Swatches CSV] Failed to delete temporary '{csv_path}': {e}", "error")

    return curve_package_path


def create_swatch_previews(*, results: Sequence[SwatchResult], preset: PresetName, asset_name: str, target_temporary_file_path: str, target_content_browser_path: str) -> Optional[str]:
# Generates temporary swatch previews as .png in the target folder.
# Assigns asset type prefix "CC" (by default) and preview suffix "prev".
# Finally, imports previews to Unreal, and after completion deletes the temporary generated files.
# Returns the created asset name for debug.

# Preparing the data:
    target_temporary_file_path: str = os.path.abspath(target_temporary_file_path)
    export_prefix: str = CUSTOM_PREFIX if CUSTOM_PREFIX else "CC"
    swatch_count: int = len(results)
    exporting_multiple: bool = (EXPORT_PRESET == "all")
    current_preset_name: str = str(preset).lower()

    if exporting_multiple:
        asset_file_name: str = f"{export_prefix}_{asset_name}_{current_preset_name}_prev"
    else:
        asset_file_name: str = f"{export_prefix}_{asset_name}_prev"

    block_size: int = SWATCH_SIZE # Generated swatch size in pixels.
    imported_asset: Optional[str] = None # DEBUG


# Generating and saving the temporary swatch previews:
    swatch_width: int = block_size * swatch_count
    swatch_height: int = block_size
    image_canvas: ImageObject = new_image("RGB", (swatch_width, swatch_height), (0, 0, 0)) # Initializes field with final dimensions, where each color swatch is pasted on.

    for i, swatch in enumerate(results):
        sampled_color: Tuple[float, float, float] = swatch["picked_color"]
        r8, g8, b8 = sampled_color
        swatch_sample: Tuple[int, int, int] = (int(round(r8)), int(round(g8)), int(round(b8)))
        swatch_tile: ImageObject = new_image("RGB", (block_size, block_size), swatch_sample)
        paste(image_canvas, swatch_tile, (i * block_size, 0))

    png_path: str = os.path.join(target_temporary_file_path, f"{asset_file_name}.png")
    save_image(image_canvas, png_path)


# Importing to Unreal:
    try:
        unreal.EditorAssetLibrary.make_directory(target_content_browser_path)

        task = unreal.AssetImportTask()
        task.filename = png_path
        task.destination_path = target_content_browser_path
        task.destination_name = asset_file_name
        task.replace_existing = True
        task.automated = True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

        asset_path = f"{target_content_browser_path}/{asset_file_name}"

        if not task.imported_object_paths or not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            log(f"[ColorSampler] Import failed: '{asset_path}'", "error")
            raise RuntimeError("Import failed")

        imported_asset = asset_path


# Deleting generated temporary files:
    finally:
        try:
            if os.path.isfile(png_path):
                os.remove(png_path)
        except Exception as e:
            log(f"[Swatch Export] Error deleting temporary file: {e}", "error")
    return imported_asset


def create_or_update_curve_atlas(*, curve_asset_name: str, curve_package_paths: Sequence[str], target_content_browser_path: str) -> Optional[str]:
# Creates or updates (if already exists) the Curve Atlas for the created curves.
# Returns Curve Atlas package path or None.

# Preparing the Curve Atlas:
    if CUSTOM_CURVE_ATLAS_PREFIX:
        atlas_name = f"{CUSTOM_CURVE_ATLAS_PREFIX}_{curve_asset_name}"
    else:
        atlas_name = f"CA_{curve_asset_name}"


    unreal.EditorAssetLibrary.make_directory(target_content_browser_path)
    atlas_package_path = f"{target_content_browser_path}/{atlas_name}"
    atlas_object_path = f"{atlas_package_path}.{atlas_name}"

    atlas_asset = None
    if unreal.EditorAssetLibrary.does_asset_exist(atlas_object_path):
        atlas_asset = unreal.EditorAssetLibrary.load_asset(atlas_object_path)

    else:
        factory = unreal.CurveLinearColorAtlasFactory()
        atlas_asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name = atlas_name,
            package_path = target_content_browser_path,
            asset_class = unreal.CurveLinearColorAtlas,
            factory = factory
        )
        if not atlas_asset:
            log(f"[Create or Update Curve Atlas] Unable to create Curve Atlas: '{atlas_package_path}'", "error")
            return None
    # Creating a new Curve Atlas.


# Loading created curve assets:
    loaded_curve_assets: list[unreal.Object] = []
    for curve_package_path in curve_package_paths:
        if not curve_package_path:
            continue
        curve_asset_name: str = curve_package_path.rsplit("/", 1)[-1]
        curve_object_path = f"{curve_package_path}.{curve_asset_name}"
        curve_asset = unreal.EditorAssetLibrary.load_asset(curve_object_path)
        if curve_asset:
            loaded_curve_assets.append(curve_asset)
        else:
            log(f"[Create or Update Curve Atlas] Unable to load selected curve: '{curve_object_path}'", "warning")


# Setting up and saving Curves in the Atlas:
    atlas_asset.set_editor_property("gradient_curves", []) # Clearing the values (in case of updating the same Curve Atlas).
    atlas_asset.set_editor_property("gradient_curves", loaded_curve_assets)

    unreal.EditorAssetLibrary.save_asset(atlas_object_path, only_if_is_dirty = False)
    return atlas_package_path




#                        === curve generator-specific color space transformations ===


def _rgb_linear_01_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
# Converts linearized RGB to Oklab color space.

    l_linear = 0.4122214708*r + 0.5363325363*g + 0.0514459929*b
    m_linear = 0.2119034982*r + 0.6806995451*g + 0.1073969566*b
    s_linear = 0.0883024619*r + 0.2817188376*g + 0.6299787005*b

    l_nonlinear = l_linear ** (1/3)
    m_nonlinear = m_linear ** (1/3)
    s_nonlinear = s_linear ** (1/3)

    l_ok = 0.2104542553*l_nonlinear + 0.7936177850*m_nonlinear - 0.0040720468*s_nonlinear
    a_ok = 1.9779984951*l_nonlinear - 2.4285922050*m_nonlinear + 0.4505937099*s_nonlinear
    b_ok = 0.0259040371*l_nonlinear + 0.7827717662*m_nonlinear - 0.8086757660*s_nonlinear
    return l_ok, a_ok, b_ok


def _oklab_to_oklch(l_ok: float, a_ok: float, b_ok: float) -> tuple[float, float, float]:
# Converts from Oklab to Oklch color space.
# Returns hue as [°].

    c = math.hypot(a_ok, b_ok)
    h = (math.degrees(math.atan2(b_ok, a_ok)) + 360.0) % 360.0
    return l_ok, c, h


def _calculate_hue_delta(hue1: float, hue2: float) -> float:
# For OKLCh color model.

    delta: float = (hue1 - hue2) % 360.0
    return 360.0 - delta if delta > 180.0 else delta




#                                             === Utils ===

def build_curve_csv_from_swatches(results: Sequence[SwatchResult]) -> str:
# Creates CSV curve from sampled swatches.

    lines: List[str] = ["Time,R,G,B"]
    for i, swatch in enumerate(results):

        time_position: float = swatch.get("rank") # CSV header; 0-1 position along the curve
        r255, g255, b255 = swatch["picked_color"]
        r: float = (r255 or 0.0) / 255.0
        g: float = (g255 or 0.0) / 255.0
        b: float = (b255 or 0.0) / 255.0
        lines.append(f"{time_position:.6f},{r:.6f},{g:.6f},{b:.6f}")

    return "\n".join(lines) + "\n"


def _falloff_gaussian(delta: float, sigma: float) -> float:
# Gaussian falloff weight for distance.

    if delta > 3.0 * sigma: return 0.0
    z = delta / max(sigma, 1e-9)
    return math.exp(-0.5 * z * z)


def _falloff_triangle(delta: float, radius: float) -> float:
# Linear triangular falloff weight for distance

    if delta >= radius: return 0.0
    return 1.0 - (delta / max(radius, 1e-9))


def _values_divide_uniform(n: int, min_value: float, max_value: float):
# Uniformly divides the texture's value range.

    if n == 1:
        return [(min_value + max_value) / 2.0]
    else:
        step: float = (max_value - min_value) / (n - 1)
        return [min_value + i_ * step for i_ in range(n)]


def _values_divide_perceptual(sorted_values: Sequence[float], quant: float) -> float:
# Uses quantiles to divide the texture's lightness more akin to the perceptual appearance.

    n: int = len(sorted_values)
    if n == 1: return float(sorted_values[0])
    position: float = quant * (n - 1)
    lower_index: int = int(math.floor(position))
    upper_index: int = int(math.ceil(position))
    if lower_index == upper_index: return float(sorted_values[lower_index])
    frac: float = position - lower_index
    return float(sorted_values[lower_index] * (1 - frac) + sorted_values[upper_index] * frac)




#                                          === Calculations ===


def _calculate_lightness_targets(lightness_list: Sequence[float], normalised_light_band_size_) -> List[float]:
# Creates lightness targets for swatches.
# Uniform - divides the texture's value range uniformly.
# Perceptual - divides the range according to the perceptual appearance of colors using quantiles.

    division_method: str = DIVISION_METHOD
    swatches_amount: int = SWATCH_COUNT
    min_perceptual_lightness_target_spacing_factor: float = MIN_PERCEPTUAL_LIGHTNESS_TARGET_SPACING_FACTOR

    if division_method == "uniform":
        min_lightness, max_lightness = min(lightness_list), max(lightness_list)
        return _values_divide_uniform(swatches_amount, min_lightness, max_lightness)

    elif division_method == "perceptual":
        lightness_list_sorted = sorted(lightness_list)
        if swatches_amount <= 1:
            lightness_targets = [_values_divide_perceptual(lightness_list_sorted, 0.5)]
        else:
            quants: List[float] = [i / (swatches_amount - 1) for i in range(swatches_amount)]
            lightness_targets: List[float] = [_values_divide_perceptual(lightness_list_sorted, quant) for quant in quants]

        if (
            min_perceptual_lightness_target_spacing_factor is not None and
            normalised_light_band_size_ is not None and
            min_perceptual_lightness_target_spacing_factor > 0.0 and
            normalised_light_band_size_ > 0.0 and
            len(lightness_targets) > 1):

            min_separation: float = normalised_light_band_size_ * min_perceptual_lightness_target_spacing_factor
            for i_ in range(1, len(lightness_targets)):
                if lightness_targets[i_] - lightness_targets[i_ - 1] < min_separation:
                    lightness_targets[i_] = min(lightness_targets[i_ - 1] + min_separation, 1.0)
        return lightness_targets

    else:
        raise ValueError(f"Unknown method: {division_method}")


def _calculate_lightness_weight(delta: float, band: float, method: LightnessWeightType) -> float:
# Computes lightness weight using the chosen method.

    band_width = max(band, 1e-9)
    if method == "gauss":
        return max(0.0, _falloff_gaussian(delta, sigma = band_width))
    return max(0.0, _falloff_triangle(delta, radius = band_width))


def _calculate_hue_weights(
    lightness_weights_: List[float],
    contributing_pixels_: List[int],
    c_oklch_list: Sequence[float],
    h_oklch_list: Sequence[float],
    *,
    hue_mode: HueModeType,
    hue_weight_method: HueWeightType,
    hue_band_size,
    collected_hue_targets: List[float],
) -> Tuple[List[float], Optional[float]]:
# For pixels above the grayness threshold, maps each pixel to the bin containing its hue (°) and accumulates its weight.
# Optionally scales bin weights by a distance-based factor from previously selected hue targets to emphasize hue diversity.
# Returns a hue target (range of hues in °) of the bin with the highest hue weights.
# Hue variables need to be updated for each mode when run 3 presets at once, so they need to be passed by the main function.

    if hue_mode not in ("dominant", "diverse"):
        return [1.0] * len(contributing_pixels_), None

    hue_repel: float = 3.0 # How far apart hue centers should be placed at.
    hue_repel_floor: float = 0.001  # Diverse hue mode only | limits the hue diversity: 0-0.005 stronger hue variations, 0,05-0.1 smoother hue changes.
    # Tweak this values.
    chroma_gray_threshold: float = CHROMA_GRAY_THRESHOLD
    eps: float = 1e-9  # Ensures non-zero range to avoid division by zero.
    hue_band_clamped: float = min(360.0, max(1.0, float(hue_band_size))) # Clamped input values.
    number_of_bins: int = 36 # Higher for finer hue resolution.
    degrees_per_bin: float = 360.0 / number_of_bins # Deriving how many degrees of hue (OKLCh) fit into each bin.
    hue_bin_weights: List[float] = [0.0] * number_of_bins # Accumulates hue weight of all the pixels that ended up in each bin. Used to derive the most dominant hue in each swatch.

# Selecting only the pixels above the set gray threshold:
    for pixel_ in contributing_pixels_:
        pixel_chroma_: float = c_oklch_list[pixel_]
        if pixel_chroma_ < chroma_gray_threshold:
            continue

        pixel_hue_: float = h_oklch_list[pixel_] # [°]
        bin_index_from_pixel_hue: int = int(pixel_hue_ / degrees_per_bin)  # Maps hues to the appropriate bin; e.g. when 10° degrees per bin: 23° / 10° = 2.3 > 2nd bin
        hue_bin_weights[bin_index_from_pixel_hue] += lightness_weights_[pixel_] * pixel_chroma_ # Adds pixel's hue weight to the appropriate bin, emphasizes more saturated pixels.

# Additional hue repulsion for the "diverse" hue mode:
    if hue_mode == "diverse" and collected_hue_targets:
        for bin_index in range(number_of_bins):
            bin_center: float = (bin_index + 0.5) * degrees_per_bin # [°]
            for previous_best_bin_center in collected_hue_targets:
                hue_delta: float = _calculate_hue_delta(bin_center, previous_best_bin_center)  # [°] the shortest distance between the current bin center and each previously collected best bin center.
                proximity: float = math.exp(-0.5 * (hue_delta / hue_band_clamped) ** 2) # Distance converted to Gaussian proximity.
                hue_bin_weights[bin_index] *= max(hue_repel_floor, 1.0 - hue_repel * proximity) # Closer hues end up with less weight due to the proximity. Due to the hue_repel_influence swatches, both sides of the lightness spectrum have less hue influence.
    # Modifies hue_weights by the factor of the bins proximity to the hue targets from the previous swatches.


    if max(hue_bin_weights) > 0.0: # In case all the pixels are below the gray threshold.
        best_bin_index = max(range(number_of_bins), key = hue_bin_weights.__getitem__) # Chooses the bin with the highest value for a given swatch - hue range with the highest accumulated weight in the given swatch.
        hue_target = (best_bin_index + 0.5) * degrees_per_bin # Best bin center [°].

        if hue_mode == "diverse":
            collected_hue_targets.append(hue_target) # Stores the selected hue target for repulsion.
    else:
        hue_target = None

    if hue_target is None:
        return [1.0] * len(contributing_pixels_), None
    # In case no targets are available, the hue weights are skipped.

    # Calculating hue weights:
    hue_weights_: List[float] = []
    chroma_softness_gamma: float = 1.0 # Controls how quickly the chroma-based softness ramps up: 1.0 = linear; >1.0 down-weights low-chroma pixels more, emphasizing saturated colors when many hues compete.

    for pixel_ in contributing_pixels_:
        pixel_chroma_: float = c_oklch_list[pixel_]
        gray_weight = min(1.0, (pixel_chroma_ / chroma_gray_threshold) ** chroma_softness_gamma)
        hue_delta_ = _calculate_hue_delta(h_oklch_list[pixel_], hue_target)

        if hue_weight_method == "gauss":
            base_weight = math.exp(-0.5 * (hue_delta_ / max(hue_band_clamped, eps)) ** 2)
        else:  # "triangle"
            base_weight = max(0.0, 1.0 - hue_delta_ / max(hue_band_clamped, eps))

        pixel_weight_: float = base_weight * gray_weight
        hue_weights_.append(pixel_weight_)

    return hue_weights_, hue_target