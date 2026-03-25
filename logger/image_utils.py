"""Image processing utilities shared across FKC modules."""

import cv2
import numpy as np
import re

# Per-region character replacement tables loaded from config.json
# ("ocr_replacements").  Each key is a region name; the value is a flat
# char → char dict.  A nested "tag" key applies replacements only to the
# alphanumeric part *after* the '#' in player-tag tokens.
_OCR_REPLACEMENTS: dict[str, dict] = {}


def load_ocr_replacements(cfg: dict) -> None:
    """Populate the module-level table from a loaded config dict."""
    _OCR_REPLACEMENTS.clear()
    _OCR_REPLACEMENTS.update(cfg.get('ocr_replacements', {}))


def apply_ocr_replacements(text: str, region_key: str) -> str:
    """Apply the flat (non-tag) OCR replacements for *region_key* to *text*."""
    for old, new in _OCR_REPLACEMENTS.get(region_key, {}).items():
        if not isinstance(new, dict):
            text = text.replace(old, new)
    return text


def sanitize_ocr_lines(text: str, region_key: str | None = None) -> list[str]:
    """Sanitize raw Tesseract output into a clean list of tokens.

    1. Apply flat character replacements for *region_key* from config.json.
    2. Strip non-alphanumeric characters (except - # _ and space).
    3. Return the last long-enough token per line (>= 7 chars).
    4. If the region config has a ``"tag"`` sub-dict, apply those
       replacements only to the ``#XXXX`` suffix of every token — useful
       for fixing digit-misreads in player tags without corrupting names.
    """
    region_cfg = _OCR_REPLACEMENTS.get(region_key, {}) if region_key else {}
    tag_repl: dict = region_cfg.get('tag', {})

    # Step 1: full-text replacements (skip nested dicts)
    for old, new in region_cfg.items():
        if not isinstance(new, dict):
            text = text.replace(old, new)

    result = []
    for raw_line in text.splitlines():
        line = re.sub(r'[^A-Za-z0-9\-\#\_\s]', ' ', raw_line).strip()
        if not line:
            continue
        splits = list(filter(lambda x: len(x) >= 7, line.split()))
        token = splits[-1] if splits else ''
        if not token:
            continue
        # Step 4: apply tag replacements only to the part after '#'
        if tag_repl and '#' in token:
            name, _, tag = token.partition('#')
            for old, new in tag_repl.items():
                tag = tag.replace(old, new)
            token = f'{name}#{tag}'
        result.append(token)
    return result


def apply_color_mask(image: np.ndarray, color_ranges: list, invert: bool = False) -> np.ndarray:
    """Apply one or more HSV color ranges to a BGR image, combined with OR.

    Args:
        image:        BGR input image.
        color_ranges: List of (lower, upper) HSV bound pairs.
                      Each element can be a numpy array or a plain Python list.
        invert:       False → matched pixels become white, rest black.
                      True  → matched pixels become black, rest white.
    Returns:
        BGR image with white pixels where mask matched (or inverted).
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    combined = np.zeros(image.shape[:2], dtype=np.uint8)
    for lower, upper in color_ranges:
        combined = cv2.bitwise_or(
            combined,
            cv2.inRange(hsv, np.asarray(lower, dtype=np.uint8),
                             np.asarray(upper, dtype=np.uint8)),
        )
    if invert:
        combined = cv2.bitwise_not(combined)
    output = np.zeros_like(image)
    output[combined > 0] = [255, 255, 255]
    return output


def capture_region(rel_bounds: dict) -> np.ndarray:
    """Grab a relative screen region and return as BGR ndarray."""
    from PIL import ImageGrab
    screen = ImageGrab.grab()
    sw, sh = screen.size
    x1 = int(rel_bounds['x1'] * sw)
    y1 = int(rel_bounds['y1'] * sh)
    x2 = int(rel_bounds['x2'] * sw)
    y2 = int(rel_bounds['y2'] * sh)
    cropped = screen.crop((x1, y1, x2, y2))
    return cv2.cvtColor(np.array(cropped), cv2.COLOR_RGB2BGR)


def apply_contrast(image: np.ndarray, contrast: float = 1.0, pivot: int = 128) -> np.ndarray:
    """Apply contrast adjustment around a brightness pivot.

    Returns image unchanged when *contrast* == 1.0.
    """
    if contrast == 1.0:
        return image
    pivot_img = np.full(image.shape, pivot, dtype=np.uint8)
    return cv2.addWeighted(image, contrast, pivot_img, 1.0 - contrast, 0)


def run_ocr(image_bgr: np.ndarray, *, psm: int = 6, whitelist: str = '',
            upscale: int = 2) -> str:
    """Run Tesseract OCR on a BGR image.

    Args:
        image_bgr: BGR input (typically a preprocessed B/W mask).
        psm:       Tesseract page segmentation mode (default: 6).
        whitelist: Optional character whitelist for Tesseract.
        upscale:   Factor to upscale before OCR (default: 2).
    Returns:
        Raw OCR text string (stripped).
    """
    import pytesseract
    config = f'--psm {psm}'
    if whitelist:
        config += f' -c tessedit_char_whitelist={whitelist}'
    h, w = image_bgr.shape[:2]
    if upscale > 1:
        image_bgr = cv2.resize(image_bgr, (w * upscale, h * upscale),
                                interpolation=cv2.INTER_CUBIC)
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    return pytesseract.image_to_string(rgb, config=config).strip()


def bgr_to_photo(bgr: np.ndarray, max_w: int = 520, max_h: int = 220):
    """Convert a BGR ndarray to a Tk PhotoImage, scaled to fit *max_w* × *max_h*.

    Never upscales the image (scale is capped at 1.0).
    """
    from PIL import Image, ImageTk
    h, w = bgr.shape[:2]
    scale = min(1.0, max_w / max(w, 1), max_h / max(h, 1))
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(bgr, (new_w, new_h))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return ImageTk.PhotoImage(Image.fromarray(rgb))
