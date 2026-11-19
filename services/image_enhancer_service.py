import io
import time
import logging
from typing import Tuple, Dict, Any, Optional
import cv2
import numpy as np
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

def enhance_image(
    image_bytes: bytes,
    target_scale: int = 4,
    resolution_mode: Optional[str] = None
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Enhance, denoise, sharpen and upscale an image to crystal-clear 2K, 4K, or 8K Super-Resolution.
    
    Modes:
      - '2k': ~1920 - 2560 px (High-Definition 2K/FHD)
      - '4k': ~3840 - 4096 px (Ultra-HD 4K Cinematic)
      - '8k': ~7680 - 8192 px (Super-Resolution 8K Wallpaper)
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
        target_dim = 7680
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
    
    # 1. Edge-preserving Denoising
    denoised = cv2.bilateralFilter(img, d=7, sigmaColor=50, sigmaSpace=50)
    
    # 2. High-Order Lanczos-4 Super-Resolution Upscaling
    upscaled = cv2.resize(denoised, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        
    # 3. Dynamic Unsharp Masking
    gaussian = cv2.GaussianBlur(upscaled, (0, 0), sigmaX=1.5, sigmaY=1.5)
    sharpened = cv2.addWeighted(upscaled, 1.4, gaussian, -0.4, 0)
    
    # 4. Contrast & Lighting Optimization via CLAHE in LAB Space
    lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)
    enhanced_bgr = cv2.cvtColor(cv2.merge([enhanced_l, a_channel, b_channel]), cv2.COLOR_LAB2BGR)
    
    # 5. Vibrance & Color Richness Boost via Pillow
    rgb_img = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    color_enhancer = ImageEnhance.Color(pil_img)
    vibrant_img = color_enhancer.enhance(1.08)
    
    # Save as high-quality JPEG
    output_buf = io.BytesIO()
    vibrant_img.save(output_buf, format="JPEG", quality=jpeg_quality, optimize=True)
    enhanced_bytes = output_buf.getvalue()
    
    elapsed = time.time() - t0
    metrics = {
        "orig_width": orig_w,
        "orig_height": orig_h,
        "new_width": new_w,
        "new_height": new_h,
        "scale": scale,
        "mode": mode_label,
        "elapsed_seconds": round(elapsed, 2)
    }
    
    return enhanced_bytes, metrics
