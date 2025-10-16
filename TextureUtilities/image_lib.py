
""" Image processing backend. Currently implemented using Pillow (PIL). PIL exports 8bit images only."""



#                                           === Backend ===

from array import array
from typing import Any, Sequence, Tuple, TypeAlias, Final, NamedTuple, Optional, List

from PIL import Image as _PIL
from PIL.Image import Image as PILImage
from PIL import Image as PILImageModule
from PIL import ImageChops

ImageObject: TypeAlias = PILImage



def apply_point_lut(image: PILImage, lut: Sequence[float], *, mode: str = "F") -> PILImage:
    return image.point(lut, mode=mode)


def close_image(image: object) -> None:
    close = getattr(image, "close", None)
    if callable(close):
        close()


def convert_mode(image: PILImage, mode: str) -> PILImage:
    return image.convert(mode)


def get_channel(image: ImageObject, ch: str) -> ImageObject:
# Extracts a single channel by name ("R","G","B","A","L")
    return image.getchannel(ch.upper())


def get_data(image: ImageObject) -> list[float | int]:
    return list(image.getdata())


def get_image_channels(image: ImageObject) -> Tuple[str, ...]:
# Returns the channel names for an already open image.
# Pillow: ("R","G","B"), ("R","G","B","A"), ("L",)
    return image.getbands()


def get_image_mode(image: Any) -> str:
# Return the Pillow image mode: "RGB", "RGBA", "L"
    return image.mode


def get_size(image: ImageObject) -> Tuple[int, int]:
# Returns the image size as (width, height)
    return image.size


def merge_channels(mode: str, channels: Sequence[Any]) -> ImageObject:
# Merge separate channels into a single image.
    return _PIL.merge(mode, tuple(channels))


def new_image(
        mode: str, size: Tuple[int, int], color: Tuple[int, int, int] | int) -> PILImage:
    return _PIL.new(mode, size, color)


def new_image_grayscale(size: Tuple[int, int], fill: int) -> Any:
# Creates a new grayscale image.
    return _PIL.new("L", size, fill)


def open_image(path: str) -> ImageObject:
    return _PIL.open(path)


def paste(dst: PILImage, src: PILImage, box: Tuple[int, int]) -> None:
    dst.paste(src, box)


def resize(image: ImageObject, size: Tuple[int, int]) -> ImageObject:
# Resize an image using bilinear resampling.
    return image.resize(size, _PIL.BILINEAR)


def resize_nearest(image: PILImage, size: Tuple[int, int]) -> PILImage:
    return image.resize(size, _PIL.NEAREST)


def save_image(image: Any, path: str) -> None:
    image.save(path)


def split_channels(image: PILImage) -> Tuple[PILImage, ...]:
    return image.split()





#                                          === Utilities ===
#                                      === Color conversion ===


class LinearChannels(NamedTuple):
    r: PILImage
    g: PILImage
    b: PILImage
    a: Optional[PILImage] = None

def _srgb_to_linear_01_lut() -> list[float]:
    lut = []
    for u8 in range(256):
        srgb01 = u8 / 255.0
        lut.append(srgb01 / 12.92 if srgb01 <= 0.04045 else ((srgb01 + 0.055) / 1.055) ** 2.4)
    return lut


_SRGB_TO_LIN_LUT: Final[list[float]] = _srgb_to_linear_01_lut()
_ALPHA8_TO_UNIT_LUT: Final[list[float]] = [u8 / 255.0 for u8 in range(256)]


def _srgb_to_linear_01_lut() -> List[float]:
# LUT for sRGB (8bit) to linear (0-1) RGB component conversion.
    lut: List[float] = []
    for u8 in range(256):
        srgb01: float = u8 / 255.0
        lut.append(srgb01 / 12.92 if srgb01 <= 0.04045 else ((srgb01 + 0.055) / 1.055) ** 2.4)
    return lut


def linear_01_to_srgb(linear01: float) -> float:
# Encodes color component from linear(0-1) to sRGB (8bit) in 0-255 range.
    linear01 = 0.0 if linear01 < 0.0 else (1.0 if linear01 > 1.0 else linear01) # Clamp
    srgb: float = 12.92 * linear01 if linear01 <= 0.0031308 else 1.055 * (linear01 ** (1 / 2.4)) - 0.055
    return 255.0 * srgb


def srgb_to_linear01(srgb: float) -> float:
# Converts images from srgb (8bit) to linear rgb in 0-1 range.
    i = int(round(srgb))
    if i < 0:
        i = 0
    elif i > 255:
        i = 255
    return float(_SRGB_TO_LIN_LUT[i])


def srgb_image_to_linear_channels_01 (image: ImageObject) -> LinearChannels:
# Converts the image from sRGB to linear RGB (0-1).
# Returns each linearized channel; Alpha just gets converted to 0-1 range.

    if image.mode == "L":
        l8 = image
        r_linear01 = l8.point(_SRGB_TO_LIN_LUT, mode="F")
        alpha_linear01 = None
        return LinearChannels(r_linear01, r_linear01, r_linear01, alpha_linear01)

    if image.mode == "RGB":
        r8, g8, b8 = image.split()
        r_linear01 = r8.point(_SRGB_TO_LIN_LUT, mode="F")
        g_linear01 = g8.point(_SRGB_TO_LIN_LUT, mode="F")
        b_linear01 = b8.point(_SRGB_TO_LIN_LUT, mode="F")
        alpha_linear01 = None
        return LinearChannels(r_linear01, g_linear01, b_linear01, alpha_linear01)

    if image.mode != "RGBA":
        image = image.convert("RGBA")
    r8, g8, b8, a8 = image.split()
    r_linear01 = r8.point(_SRGB_TO_LIN_LUT, mode="F")
    g_linear01 = g8.point(_SRGB_TO_LIN_LUT, mode="F")
    b_linear01 = b8.point(_SRGB_TO_LIN_LUT, mode="F")
    alpha_linear01 = a8.point(_ALPHA8_TO_UNIT_LUT, mode="F")
    return LinearChannels(r_linear01, g_linear01, b_linear01, alpha_linear01)




#                                         === Utility functions ===

def are_channels_equal(image: ImageObject, input_channel1: str, input_chanel2: str) -> bool:
# Returns True if both channels are identical.

    try:
        channel1 = get_channel(image, input_channel1)
        channel2 = get_channel(image, input_chanel2)
        return ImageChops.difference(channel1, channel2).getbbox() is None
    except Exception:
        return False


def convert_to_grayscale(image: ImageObject) -> ImageObject:
# Converts an image to 8-bit grayscale.
    mode = image.mode
    if mode == "L":
        return image
    if mode in ("I", "I;16", "I;16L", "I;16B"):
        return _16_to_8bit(image)
    return image.convert("L")


def is_grayscale(image: ImageObject) -> bool:
# Returns True if the image is of type grayscale image.

    mode = get_image_mode(image)
    return mode in ("L", "LA") or mode == "I" or str(mode).startswith("I;16")


def is_rgb_grayscale(image: ImageObject) -> bool:
# Checks if RGB texture is just a grayscale image saved as RGB instead of L.

    try:
        ext = image.getextrema()  # (Rmin,Rmax),(Gmin,Gmax),(Bmin,Rmax),(Amin,Amax)
        if not ext or len(ext) < 2 or ext[0] != ext[1]:
            return False
        # Pre-validation: checks if the channels extremes are the same.

    except Exception:
        pass
    return are_channels_equal(image, "R", "G")


def _16_to_8bit(image: ImageObject) -> ImageObject:
# Scales down 16bit range to a 8bit, so values are properly maintained instead of being clipped.

# Preparing the image:
    if image.mode == "I":
        img16 = image.convert("I;16")
    elif image.mode in ("I;16", "I;16L", "I;16B"):
        img16 = image if image.mode == "I;16" else image.convert("I;16")
    # Normalizes the image type to 16bit LE.
    else:
        return image.convert("L")
    # If the image is just 8bit grayscale, passes it though.

    raw = img16.tobytes("raw", "I;16")  # LE 16bit
    data16 = array("H")
    data16.frombytes(raw)

# Scaling:
    data8 = bytearray((v >> 8) & 0xFF for v in data16)
    return PILImageModule.frombytes("L", img16.size, bytes(data8))