"""Image processing utilities shared across FKC modules."""

import cv2
import numpy as np
import re


def sanitize_ocr_lines(text: str) -> list[str]:
    """Sanitize raw Tesseract output into a clean list of tokens.
    Returns a list of non-empty last-word tokens.
    """
    result = []
    for raw_line in text.splitlines():
        line = re.sub(r'[^A-Za-z0-9\-\#\_\s]', ' ', raw_line).strip()
        if not line:
            continue
        splits = list(filter(lambda x: len(x) >= 7, line.split()))
        token = splits[-1] if splits else ''
        if token:
            result.append(token)
    return result


def apply_color_mask(image: np.ndarray, color_ranges: list, invert: bool = False) -> np.ndarray:
    """Apply one or more HSV color ranges to a BGR image, combined with OR.

    Args:
        image:        BGR input image.
        color_ranges: List of (lower, upper) np.array HSV bound pairs.
        invert:       False → matched pixels become white, rest black
                             (white-on-black; good for highlight extraction).
                      True  → matched pixels become black, rest white
                             (dark-on-light; preferred by Tesseract).
    Returns:
        BGR image.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    combined = np.zeros(image.shape[:2], dtype=np.uint8)
    for lower, upper in color_ranges:
        combined = cv2.bitwise_or(combined, cv2.inRange(hsv, lower, upper))
    if invert:
        combined = cv2.bitwise_not(combined)
    output = np.zeros_like(image)
    output[combined > 0] = [255, 255, 255]
    return output
