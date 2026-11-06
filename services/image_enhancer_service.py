import io
import time
import logging
from typing import Tuple, Dict, Any
import cv2
import numpy as np
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

def enhance_image(image_bytes: bytes, target_scale: int = 2) -> Tuple[bytes, Dict[str, Any]]:
    """
    Enhance, denoise, sharpen and upscale an image to high-definition quality.
    
    Steps:
      1. Edge-preserving bilateral denoising to remove compression artifacts.
      2. Super-resolution upscaling (Lanczos-4 interpolation).
      3. Unsharp masking to accentuate fine textures, facial lines, and contours.
      4. CLAHE on LAB color space to optimize dynamic range & local contrast.
      5. Subtle color vibrance tuning via Pillow.
    """
    t0 = time.time()
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("Could not decode image from provided bytes.")
        
    orig_h, orig_w = img.shape[:2]
    
    # Determine adaptive scale factor
    # If image is very small (< 400px), upscale 4x; otherwise 2x
    if max(orig_w, orig_h) <= 450:
        scale = max(target_scale, 4)
    elif max(orig_w, orig_h) >= 2000:
        scale = 1  # Already high-res; focus on denoising + sharpening + contrast
    else:
        scale = target_scale
        
    new_w = min(orig_w * scale, 4096)
    new_h = min(orig_h * scale, 4096)
    
    # 1. Edge-preserving Denoising
    denoised = cv2.bilateralFilter(img, d=7, sigmaColor=50, sigmaSpace=50)
    
    # 2. High-Order Lanczos-4 Upscaling
    if scale > 1:
        upscaled = cv2.resize(denoised, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    else:
        upscaled = denoised
        new_w, new_h = orig_w, orig_h
        
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
    vibrant_img.save(output_buf, format="JPEG", quality=95, optimize=True)
    enhanced_bytes = output_buf.getvalue()
    
    elapsed = time.time() - t0
    metrics = {
        "orig_width": orig_w,
        "orig_height": orig_h,
        "new_width": new_w,
        "new_height": new_h,
        "scale": scale,
        "elapsed_seconds": round(elapsed, 2)
    }
    
    return enhanced_bytes, metrics
