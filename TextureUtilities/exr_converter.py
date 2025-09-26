
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

        cp: subprocess.CompletedProcess[str] = subprocess.run([pyexe, "-c", code], **kwargs)
        return (cp.returncode == 0) and ((cp.stdout or "").strip() == "1")
        # Subprocess

    except Exception:
        return False


def exr_to_image(src_exr: str, *, ext: str = "png", srgb_transform: bool = True):
# Converts a .exr file to a bitmap by running Unreal Engine’s embedded Python in a child process, avoiding DLL/import conflicts that can occur when run inside the Engine.
# Returns an absolute path to the converted image.

# Creating the directory:
    ext: str = "." + ext
    src_path: tuple[str, str] = os.path.splitext(src_exr)
    base, _ = src_path
    fin_path: str = base + ext
    os.makedirs(os.path.dirname(os.path.abspath(fin_path)) or ".", exist_ok=True)

# Launching the subprocess:
    pyexe: str = _ue_python_exe()
    env: dict[str, str] = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONIOENCODING"] = "utf-8"  # Forced utf-8 encoding to mitigate UnicodeDecodeError.

    args: list[str] = [
        pyexe,
        "-c", "import sys; exec(sys.stdin.read())",  # -c
        src_exr,
        fin_path,
        ext.lstrip("."),
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


    except subprocess.CalledProcessError as e:
        err: str = (e.stderr or e.stdout or "").strip()
        if SHOW_DETAILS and err:
            log(f"Exr to image subprocess failed {e.returncode} for '{src_exr}': {err}", "error")
        return None

    except Exception as e:
        if SHOW_DETAILS:
            log(f"Exr to image subprocess exception for '{src_exr}': {e}", "error")
        return None
    # Error logs.

    if not os.path.isfile(fin_path):
        if SHOW_DETAILS:
            log(f"Exr to image subprocess failed: output not found (expected '{fin_path}')", "error")
        return None
    # Checks created image.

    try:
        os.remove(src_exr)
    except Exception as e:
        if SHOW_DETAILS:
            log(f"Exr to image subprocess: couldn't delete source '{src_exr}': {e}", "warn")
    # Deletes the original .exr file.
    return os.path.abspath(fin_path).replace("\\", "/")


def _is_executable(path: str) -> bool:
# Returns True if a path points to an existing executable file.

    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


@lru_cache(maxsize=1)
def _ue_python_exe() -> str:
# Builds a path to the current Unreal Engine’s embedded Python .exe.

    def get_abs_path(rel: str) -> str:
    # Converts engine's interpreter relative path to absolute.
        return os.path.abspath(os.path.normpath(os.path.join(eng, rel)))

    candidates: list[str] = []
    try:
        import unreal
        eng: str = unreal.Paths.engine_dir()


        if not os.path.isabs(eng):
            try:
                eng = unreal.Paths.convert_relative_path_to_full(eng)
            except Exception:
                eng = os.path.abspath(os.path.normpath(os.path.join(os.getcwd(), eng)))

        if sys.platform.startswith("win"):
            candidates += [get_abs_path(r"Binaries/ThirdParty/Python3/Win64/python.exe")]
        elif sys.platform.startswith("linux"):
            candidates += [get_abs_path("Binaries/ThirdParty/Python3/Linux/bin/python3")]
        elif sys.platform == "darwin":
            candidates += [get_abs_path("Binaries/ThirdParty/Python3/Mac/bin/python3"), get_abs_path("Binaries/ThirdParty/Python3/Mac/Frameworks/Python.framework/Versions/Current/bin/python3")]
    except Exception as e:
        try:
            log(f" UE python.exe: couldn't query Unreal Engine path ({type(e).__name__}: {e})", "warn")
        except Exception:
            pass
    # Tries to derive Unreal's Python interpreter path.

    sys_fb: list[str] = [p for p in (shutil.which("python3"), shutil.which("python")) if p]
    if sys_fb:
        candidates.extend(sys_fb)
        try:
            log("Fallback to system's Python interpreter.", "warn")
        except Exception:
            pass
    # Fallback to a system's interpreter.


    for c in candidates:
        if _is_executable(c):
            if SHOW_DETAILS:
                log(f"Using interpreter: {c}", "info")
            return c
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

    src: str = sys.argv[1]
    dst: str = sys.argv[2]
    ext: str = sys.argv[3].lower()
    do_srgb: bool = (sys.argv[4] == "1")

    # Preparing the image:
    file: "OpenEXR.InputFile" = OpenEXR.InputFile(src)
    hdr: "dict[str, object]" = file.header()
    dw: "Imath.Box2i" = hdr["dataWindow"]
    width: int = dw.max.x - dw.min.x + 1
    height: int = dw.max.y - dw.min.y + 1
    float_pix: "Imath.PixelType" = Imath.PixelType(Imath.PixelType.FLOAT)  # Setting pixel data type to float.

    channels_list: "list[str]" = list(hdr["channels"].keys())
    ch_names: "dict[str, str]" = {n.lower(): n for n in channels_list}
    # Gets names of all available channels.


    def linear_to_srgb(x: "np.ndarray") -> "np.ndarray":
        # Applies sRGB gamma.
        x = np.clip(x, 0.0, 1.0).astype(np.float32)
        a: float = 0.055
        return np.where(x <= 0.0031308, x * 12.92, (1 + a) * np.power(x, 1/2.4) - a)
    
    
    def read_channel(n: str) -> "np.ndarray":
        # Reads channel as a 32b float and restructures its pixels into 2D array W*H.
        return np.frombuffer(file.channel(n, float_pix), dtype=np.float32).reshape(height, width)


    has_rgb: bool = all(k in ch_names for k in ("r", "g", "b"))
    has_a: bool = ("a" in ch_names)

    save_kwargs: "dict[str, object]" = {"quality": 95, "optimize": True} if ext == "jpg" else {}
    # Setting quality for jpeg export.

    # Processing the image:
    if has_rgb:
        r: "np.ndarray" = read_channel(ch_names["r"])
        g: "np.ndarray" = read_channel(ch_names["g"])
        b: "np.ndarray" = read_channel(ch_names["b"])
        rgb: "np.ndarray" = np.stack([r, g, b], axis=-1)  # Creates a NumPy array combining all RGB channels: HxWx3 (Height, Width, Channels).

        looks_empty_alpha: bool = True
        a: Optional[np.ndarray] = None

        if has_a:
            a = read_channel(ch_names["a"])[..., None]
            eps: float = 1e-6
            a_min: float = float(a.min())
            a_max: float = float(a.max())
            looks_empty_alpha = a_max <= eps
            looks_opaque_alpha: bool = a_min >= 1.0 - eps
            mid_ratio: float = float(((a > eps) & (a < 1.0 - eps)).mean())
            do_unpremul: bool = (not looks_empty_alpha) and (not looks_opaque_alpha) and (mid_ratio > 0.001)
            
            if do_unpremul:
                denom: "np.ndarray" = np.maximum(a, np.float32(1e-8))
                rgb = np.divide(rgb, denom, out=rgb, where=denom > 0).astype(np.float32)
        # Un-premultiplies Alpha if available, and is neither all 0 nor 1.

        if do_srgb:
            rgb = linear_to_srgb(rgb)

        # Converting to 8bit int. Generating and saving the image:
        if looks_empty_alpha or ext == "jpg":
            out_u8: "np.ndarray" = np.rint(np.clip(rgb, 0, 1) * 255.0).astype("uint8")
            Image.fromarray(out_u8, "RGB").save(dst, **save_kwargs)
        else:
            rgba: "np.ndarray" = np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0.0, 1.0)], axis=-1)  # type: ignore[arg-type]
            out_u8 = np.rint(rgba * 255.0).astype("uint8")
            Image.fromarray(out_u8, "RGBA").save(dst, **save_kwargs)
    # Converting the RGB file.

    else:
        # In case the full RGB is missing, it extracts the first available channel.
        y: "np.ndarray" = read_channel(channels_list[0])
        if do_srgb:
            y = linear_to_srgb(y)
        out_u8: "np.ndarray" = np.rint(np.clip(y, 0, 1) * 255.0).astype("uint8")  # Converting to 8bit int.
        Image.fromarray(out_u8, "L").save(dst, **save_kwargs)
    # Converting the Grayscale file.
    
    
    file.close()

if __name__ == "__main__":
    main()
""")