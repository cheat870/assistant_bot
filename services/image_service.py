import io
import logging
import asyncio
from typing import Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)

def _remove_background_sync(image_bytes: bytes) -> io.BytesIO:
    """Remove background from image bytes using OpenCV GrabCut segmentation."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("មិនអាចអាន File រូបភាពនេះបានឡើយ")

    height, width = img.shape[:2]
    # Downscale for performance if very large
    max_dim = 1200
    scale = 1.0
    if max(height, width) > max_dim:
        scale = max_dim / float(max(height, width))
        new_w, new_h = int(width * scale), int(height * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        height, width = new_h, new_w

    # Create GrabCut initial bounding box (leaving small border around edges)
    border_x = max(int(width * 0.04), 2)
    border_y = max(int(height * 0.04), 2)
    rect = (border_x, border_y, width - (2 * border_x), height - (2 * border_y))

    mask = np.zeros((height, width), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    # 4 iterations provides good balance between quality and speed (<1.5s)
    cv2.grabCut(img, mask, rect, bgd_model, fgd_model, 4, cv2.GC_INIT_WITH_RECT)

    # Foreground pixels are 1 (definite FG) and 3 (probable FG)
    fg_mask = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)

    # Smooth the mask edges slightly
    fg_mask = cv2.GaussianBlur(fg_mask, (3, 3), 0)

    # Construct RGBA transparent image
    b, g, r = cv2.split(img)
    rgba = cv2.merge([b, g, r, fg_mask])

    success, encoded_png = cv2.imencode(".png", rgba)
    if not success:
        raise RuntimeError("បរាជ័យក្នុងការបង្កើត File PNG Transparent")

    out_fp = io.BytesIO(encoded_png.tobytes())
    out_fp.seek(0)
    return out_fp

async def remove_background(image_bytes: bytes) -> io.BytesIO:
    """Async wrapper for background removal."""
    return await asyncio.to_thread(_remove_background_sync, image_bytes)
