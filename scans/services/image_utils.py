"""
Image processing utilities: resize, strip EXIF, validate.
"""

import io
import logging

logger = logging.getLogger(__name__)

MAX_DIMENSION = 1024
JPEG_QUALITY = 85
MAX_FILE_BYTES = 8 * 1024 * 1024  # 8 MB


def process_image(image_bytes: bytes, filename: str) -> tuple[bytes, str]:
    """
    Validate, strip EXIF GPS, and resize image.

    Returns (processed_bytes, mime_type) or raises ValueError.
    """
    try:
        from PIL import Image, ExifTags
    except ImportError:
        raise ValueError("Pillow o'rnatilmagan. 'pip install Pillow' buyrug'ini bajaing.")

    if len(image_bytes) > MAX_FILE_BYTES:
        raise ValueError("Rasm hajmi 8 MB dan oshmasligi kerak.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = {"jpg", "jpeg", "png", "webp"}
    if ext not in allowed:
        raise ValueError("Faqat JPG, PNG yoki WEBP formatdagi rasmlar qabul qilinadi.")

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
        img = Image.open(io.BytesIO(image_bytes))  # reopen after verify
    except Exception:
        raise ValueError("Rasm fayli o'qilmadi yoki buzilgan.")

    # Convert to RGB (handles RGBA, P, etc.)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Strip GPS EXIF data (keep other EXIF for now, safer approach is strip all)
    try:
        exif = img.getexif()
        # GPS IFD tag is 34853
        GPS_IFD_TAG = 34853
        if GPS_IFD_TAG in exif:
            del exif[GPS_IFD_TAG]
    except Exception:
        exif = None

    # Resize if too large
    w, h = img.size
    if max(w, h) > MAX_DIMENSION:
        ratio = MAX_DIMENSION / max(w, h)
        new_w, new_h = int(w * ratio), int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    save_kwargs = {"format": "JPEG", "quality": JPEG_QUALITY, "optimize": True}
    img.save(buf, **save_kwargs)
    processed_bytes = buf.getvalue()
    return processed_bytes, "image/jpeg"
