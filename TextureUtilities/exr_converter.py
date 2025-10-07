
""" EXR conversion executed in UE’s embedded-Python subprocess to avoid editor crashes from DLL conflicts during OpenEXR/Imath imports. """


import os
import shutil
import subprocess
import sys
import textwrap

from functools import lru_cache

from ..common_utils import log
from .texture_settings import SHOW_DETAILS


@lru_cache(maxsize=1)
def check_exr_libraries() -> bool:
# Checks in a separate process if the necessary libraries are available.

    pyexe: str = _ue_python_exe()
    code: str = (
        "import importlib.util as iu; "
        "exr=bool(iu.find_spec('openexr') or iu.find_spec('OpenEXR')); "
        "npy=bool(iu.find_spec('numpy')); "
        "print(int(exr and npy))"
    )
    try:
        kwargs: dict[str, bool] = dict(capture_output=True, text=True)
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) # Hides the CLI windows for the library check.

        completed_process: subprocess.CompletedProcess[str] = subprocess.run([pyexe, "-c", code], **kwargs)
        return (completed_process.returncode == 0) and ((completed_process.stdout or "").strip() == "1")
        # Subprocess

    except Exception:
        return False


def exr_to_image(source_exr: str, *, output_extension: str = "png", srgb_transform: bool = True):
# Converts a .exr file to a bitmap by running Unreal Engine’s embedded Python in a child process, avoiding DLL/import conflicts that can occur when run inside the Engine.
# Returns an absolute path to the converted image.

# Creating the directory:
    output_extension: str = "." + output_extension
    source_path: tuple[str, str] = os.path.splitext(source_exr)
    source_filename, _ = source_path
    target_path: str = source_filename + output_extension
    os.makedirs(os.path.dirname(os.path.abspath(target_path)) or ".", exist_ok=True)

# Launching the subprocess:
    pyexe: str = _ue_python_exe()
    env: dict[str, str] = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONIOENCODING"] = "utf-8"  # Forced utf-8 encoding to mitigate UnicodeDecodeError.

    args: list[str] = [
        pyexe,
        "-c", "import sys; exec(sys.stdin.read())",  # -c
        source_exr,
        target_path,
        output_extension.lstrip("."),
        "1" if srgb_transform else "0",
    ]

    kwargs: dict[str, object] = dict(
        input=_exr_helper_code(),
        text=True,
        capture_output=True,
        check=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )

    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Hides the CLI windows.
    try:
        subprocess.run(args, **kwargs)


    except subprocess.CalledProcessError as error:
        process_output_error: str = (error.stderr or error.stdout or "").strip()
        if SHOW_DETAILS and process_output_error:
            log(f"Exr to image subprocess failed {error.returncode} for '{source_exr}': {process_output_error}", "error")
        return None

    except Exception as error:
        if SHOW_DETAILS:
            log(f"Exr to image subprocess exception for '{source_exr}': {error}", "error")
        return None
    # Error logs.

    if not os.path.isfile(target_path):
        if SHOW_DETAILS:
            log(f"Exr to image subprocess failed: output not found (expected '{target_path}')", "error")
        return None
    # Checks created image.

    try:
        os.remove(source_exr)
    except Exception as error:
        if SHOW_DETAILS:
            log(f"Exr to image subprocess: couldn't delete source '{source_exr}': {error}", "warn")
    # Deletes the original .exr file.
    return os.path.abspath(target_path).replace("\\", "/")


def _is_executable(exe_path: str) -> bool:
# Returns True if a path points to an existing executable file.

    return bool(exe_path) and os.path.isfile(exe_path) and os.access(exe_path, os.X_OK)


@lru_cache(maxsize=1)
def _ue_python_exe() -> str:
# Builds a path to the current Unreal Engine’s embedded Python .exe.

    def get_absolute_path(relative_path: str) -> str:
    # Converts engine's interpreter relative path to absolute.
        return os.path.abspath(os.path.normpath(os.path.join(eng, relative_path)))

    os_candidates: list[str] = []
    try:
        import unreal
        eng: str = unreal.Paths.engine_dir()


        if not os.path.isabs(eng):
            try:
                eng = unreal.Paths.convert_relative_path_to_full(eng)
            except Exception:
                eng = os.path.abspath(os.path.normpath(os.path.join(os.getcwd(), eng)))

        if sys.platform.startswith("win"):
            os_candidates += [get_absolute_path(r"Binaries/ThirdParty/Python3/Win64/python.exe")]
        elif sys.platform.startswith("linux"):
            os_candidates += [get_absolute_path("Binaries/ThirdParty/Python3/Linux/bin/python3")]
        elif sys.platform == "darwin":
            os_candidates += [get_absolute_path("Binaries/ThirdParty/Python3/Mac/bin/python3"), get_absolute_path("Binaries/ThirdParty/Python3/Mac/Frameworks/Python.framework/Versions/Current/bin/python3")]
    except Exception as error:
        try:
            log(f" UE python.exe: couldn't query Unreal Engine path ({type(error).__name__}: {error})", "warn")
        except Exception:
            pass
    # Tries to derive Unreal's Python interpreter path.

    system_fallback_interpreters: list[str] = [p for p in (shutil.which("python3"), shutil.which("python")) if p]
    if system_fallback_interpreters:
        os_candidates.extend(system_fallback_interpreters)
        try:
            log("Fallback to system's Python interpreter.", "warn")
        except Exception:
            pass
    # Fallback to a system's interpreter.


    for candidate_path in os_candidates:
        if _is_executable(candidate_path):
            if SHOW_DETAILS:
                log(f"Using interpreter: {candidate_path}", "info")
            return candidate_path
    # Returns the first executable interpreter.

    log("UE python.exe: no Python interpreter found.", "error")
    return ""


@lru_cache(maxsize=1)
def _exr_helper_code() -> str:
# Returns the helper script (text) used by the subprocess to convert 32-bit EXR to 8-bit images with OpenEXR+NumPy.
    return textwrap.dedent(r"""# -*- coding: utf-8 -*-
import sys
from typing import Optional

import OpenEXR
import Imath
import numpy as np
from PIL import Image


def main() -> None:

    source_exr_path: str = sys.argv[1]
    output_path: str = sys.argv[2]
    file_extension: str = sys.argv[3].lower()
    srgb_tone_map: bool = (sys.argv[4] == "1")

    # Preparing the image:
    file: "OpenEXR.InputFile" = OpenEXR.InputFile(source_exr_path)
    hdr: "dict[str, object]" = file.header()
    data_window: "Imath.Box2i" = hdr["dataWindow"]
    width: int = data_window.max.x - data_window.min.x + 1
    height: int = data_window.max.y - data_window.min.y + 1
    float_pixel_data: "Imath.PixelType" = Imath.PixelType(Imath.PixelType.FLOAT)  # Setting pixel data type to float.

    channels_list: "list[str]" = list(hdr["channels"].keys())
    channel_names: "dict[str, str]" = {channel.lower(): channel for channel in channels_list}
    # Gets names of all available channels.


    def linear_to_srgb(linear_values: "np.ndarray") -> "np.ndarray":
        # Applies sRGB gamma.
        linear_values = np.clip(linear_values, 0.0, 1.0).astype(np.float32)
        srgb_a: float = 0.055
        return np.where(linear_values <= 0.0031308, linear_values * 12.92, (1 + srgb_a) * np.power(linear_values, 1/2.4) - srgb_a)
    
    
    def read_channel(channel_name: str) -> "np.ndarray":
        # Reads channel as a 32b float and restructures its pixels into 2D array W*H.
        return np.frombuffer(file.channel(channel_name, float_pixel_data), dtype=np.float32).reshape(height, width)


    is_rgb: bool = all(channel in channel_names for channel in ("r", "g", "b"))
    has_alpha: bool = ("a" in channel_names)

    save_kwargs: "dict[str, object]" = {"quality": 95, "optimize": True} if file_extension == "jpg" else {}
    # Setting quality for jpeg export.

    # Processing the image:
    if is_rgb:
        r: "np.ndarray" = read_channel(channel_names["r"])
        g: "np.ndarray" = read_channel(channel_names["g"])
        b: "np.ndarray" = read_channel(channel_names["b"])
        rgb: "np.ndarray" = np.stack([r, g, b], axis=-1)  # Creates a NumPy array combining all RGB channels: HxWx3 (Height, Width, Channels).

        almost_empty_alpha: bool = True
        alpha: Optional[np.ndarray] = None

        if has_alpha:
            alpha: NDArray[np.float32] = read_channel(channel_names["a"])[..., None]
            eps: float = 1e-6
        
            a_min: float = float(alpha.min())
            a_max: float = float(alpha.max())
        
            is_almost_empty: bool = a_max <= eps
            is_almost_opaque: bool = a_min >= 1.0 - eps
        
            if not is_almost_empty and not is_almost_opaque:
                partial_alpha_fraction = float(((alpha > eps) & (alpha < 1.0 - eps)).mean())
                if partial_alpha_fraction > 1e-3:
                    alpha_denominator: NDArray[np.float32] = np.maximum(alpha, np.float32(1e-8))
                    rgb = np.divide(rgb, alpha_denominator, out=rgb, where=alpha_denominator > 0).astype(np.float32)
        # Un-premultiplies Alpha if available, and is neither all 0 nor 1.

        if srgb_tone_map:
            rgb = linear_to_srgb(rgb)

        # Converting to 8bit int. Generating and saving the image:
        if almost_empty_alpha or file_extension == "jpg":
            output_image_u8: "np.ndarray" = np.rint(np.clip(rgb, 0, 1) * 255.0).astype("uint8")
            Image.fromarray(output_image_u8, "RGB").save(output_path, **save_kwargs)
        else:
            rgba: "np.ndarray" = np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0.0, 1.0)], axis=-1)  # type: ignore[arg-type]
            output_image_u8 = np.rint(rgba * 255.0).astype("uint8")
            Image.fromarray(output_image_u8, "RGBA").save(output_path, **save_kwargs)
    # Converting the RGB file.

    else:
        # Extracting the first available channel, in case the full RGB is missing:
        grayscale: "np.ndarray" = read_channel(channels_list[0])
        if srgb_tone_map:
            grayscale = linear_to_srgb(grayscale)
        output_image_u8: "np.ndarray" = np.rint(np.clip(grayscale, 0, 1) * 255.0).astype("uint8")  # Converting to 8bit int.
        Image.fromarray(output_image_u8, "L").save(output_path, **save_kwargs)
    # Converting the Grayscale file.
    
    
    file.close()

if __name__ == "__main__":
    main()
""")