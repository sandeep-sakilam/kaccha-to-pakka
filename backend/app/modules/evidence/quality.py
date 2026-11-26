"""Server-side image checks. The phone already checks blur and glare before upload; this repeats
the cheap checks and refuses photos that are clearly not live captures."""

import io
from dataclasses import dataclass
from datetime import datetime, timedelta

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

MIN_SIDE = 480
BLUR_MIN_VARIANCE = 60.0
DARK_MEAN = 40.0
BRIGHT_MEAN = 250.0  # paper is bright; only a washed-out frame fails


@dataclass(frozen=True)
class ImageCheck:
    ok: bool
    reason: str | None
    width: int
    height: int
    sharpness: float
    brightness: float
    exif_taken_at: datetime | None


def check_image(data: bytes, captured_at: datetime) -> ImageCheck:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        return ImageCheck(False, "not_an_image", 0, 0, 0, 0, None)
    w, h = img.size
    exif_at: datetime | None = None
    try:
        raw = img.getexif().get(36867) or img.getexif().get(306)  # DateTimeOriginal / DateTime
        if raw:
            exif_at = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S").replace(
                tzinfo=captured_at.tzinfo
            )
    except (ValueError, TypeError):
        exif_at = None
    gray = img.convert("L")
    gray.thumbnail((640, 640))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    ew, eh = edges.size
    edges = edges.crop((2, 2, ew - 2, eh - 2))  # the filter marks the frame border itself
    sharp = float(ImageStat.Stat(edges).var[0])
    bright = float(ImageStat.Stat(gray).mean[0])
    reason = None
    if min(w, h) < MIN_SIDE:
        reason = "too_small"
    elif bright < DARK_MEAN:
        reason = "too_dark"
    elif bright > BRIGHT_MEAN:
        reason = "too_bright"
    elif sharp < BLUR_MIN_VARIANCE:
        reason = "blurry"
    elif exif_at is not None and abs(captured_at - exif_at) > timedelta(hours=24):
        reason = "not_live"  # an old gallery photo re-sent as a capture
    return ImageCheck(reason is None, reason, w, h, round(sharp, 1), round(bright, 1), exif_at)
