"""
Uploaded photos are re-encoded before saving:

- downscaled so a free storage tier lasts (ADR 0005);
- EXIF metadata is dropped — phone photos often carry the GPS position of
  the recipient's home, which would defeat the hidden-address rule.
"""

from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps

REQUEST_PHOTO_MAX = 1280
AVATAR_MAX = 400


def shrink(uploaded, max_side, quality=82):
    """Return a JPEG copy no larger than max_side px, without metadata."""
    with Image.open(uploaded) as original:
        image = ImageOps.exif_transpose(original)  # keep the visual orientation
        image.thumbnail((max_side, max_side))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)  # no exif= → stripped
    name = Path(uploaded.name).stem + ".jpg"
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")
