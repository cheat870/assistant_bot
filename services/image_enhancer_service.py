import io
import time
import gc
import logging
from typing import Tuple, Dict, Any, Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)

def enhance_image(
    image_bytes: bytes,
    target_scale: int = 4,
    resolution_mode: Optional[str] = None
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Enhance, denoise, sharpen and upscale an image to crystal-clear 2K, 4K, or 8K Super-Resolution.
    Uses an ultra-fast, memory-optimized pipeline designed to safely run on cloud instances with 512MB RAM.
    
    Modes:
      - '2k': ~1920 - 2560 px (High-Definition 2K/FHD)
      - '4k': ~3840 - 4096 px (Ultra-HD 4K Cinematic)
      - '8k': ~6144 - 8192 px (Super-Resolution 8K Wallpaper)
    """
    t0 = time.time()
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("Could not decode image from provided bytes.")
        
    orig_h, orig_w = img.shape[:2]
    max_orig = max(orig_w, orig_h)

    # Determine mode from parameter or target_scale
    norm_mode = (resolution_mode or "").lower().strip()
    if not norm_mode:
        if target_scale >= 8:
            norm_mode = "8k"
        elif target_scale >= 4:
            norm_mode = "4k"
        else:
            norm_mode = "2k"

    if norm_mode == "8k":
        target_dim = 6144
        cap = 8192
        mode_label = "8K Super-Res"
        jpeg_quality = 93
    elif norm_mode == "4k":
        target_dim = 3840
        cap = 4096
        mode_label = "4K Ultra"
        jpeg_quality = 95
    else: # 2k
        target_dim = 1920
        cap = 2560
        mode_label = "2K HD"
        jpeg_quality = 95

    # Compute exact scale factor to reach desired dimension
    scale = max(2, round(target_dim / max_orig))
    new_w = min(orig_w * scale, cap)
    new_h = min(orig_h * scale, cap)
    
    # 1. Edge-preserving Denoising on source image (< 5 MB RAM)
    denoised = cv2.bilateralFilter(img, d=7, sigmaColor=50, sigmaSpace=50)
    del img
    
    # 2. CLAHE Dynamic Range on source image (< 5 MB RAM)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    del denoised
    l_chan, a_chan, b_chan = cv2.split(lab)
    del lab
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
    l_chan = clahe.apply(l_chan)
    enhanced_src = cv2.cvtColor(cv2.merge([l_chan, a_chan, b_chan]), cv2.COLOR_LAB2BGR)
    del l_chan, a_chan, b_chan
    
    # 3. Super-Resolution Upscaling directly to target dimensions (Lanczos-4)
    upscaled = cv2.resize(enhanced_src, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    del enhanced_src
    gc.collect()

    # 4. Sharpening via fast 3x3 convolution
    kernel = np.array([[0, -0.15, 0], [-0.15, 1.6, -0.15], [0, -0.15, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(upscaled, -1, kernel)
    del upscaled
    gc.collect()

    # 5. Direct JPEG encode for full resolution file
    _, full_buf = cv2.imencode(".jpg", sharpened, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    full_bytes = full_buf.tobytes()

    # 6. If width + height > 9500 (Telegram sendPhoto API limit), generate visual preview photo
    preview_bytes = None
    if (new_w + new_h) > 9500:
        prev_scale = 4000.0 / max(new_w, new_h)
        pw, ph = int(new_w * prev_scale), int(new_h * prev_scale)
        prev_img = cv2.resize(sharpened, (pw, ph), interpolation=cv2.INTER_AREA)
        _, prev_buf = cv2.imencode(".jpg", prev_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        preview_bytes = prev_buf.tobytes()
        del prev_img

    del sharpened
    gc.collect()
    
    elapsed = time.time() - t0
    metrics = {
        "orig_width": orig_w,
        "orig_height": orig_h,
        "new_width": new_w,
        "new_height": new_h,
        "scale": scale,
        "mode": mode_label,
        "elapsed_seconds": round(elapsed, 2),
        "needs_document_only": (new_w + new_h) > 9500,
        "preview_bytes": preview_bytes
    }
    
    return full_bytes, metrics
