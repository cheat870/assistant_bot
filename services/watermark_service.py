import io
import os
import math
import logging
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Font candidates for Windows & Linux environments
FONT_CANDIDATES = [
    # Windows paths
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/Leelawad.ttf",
    "C:/Windows/Fonts/Nirmala.ttf",
    # Linux (Render / Docker) paths
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

def _get_font(size: int) -> ImageFont.ImageFont:
    """Load an available TrueType font or fallback to default."""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def apply_watermark(
    image_bytes: bytes,
    text: str,
    position: str = "bottom_right",
    style: str = "badge",
    opacity: int = 180
) -> bytes:
    """
    Apply a professional, stylish semi-transparent watermark to an image.
    
    Args:
        image_bytes: Raw bytes of the image
        text: Watermark text (brand, store name, phone number, etc.)
        position: 'bottom_right', 'bottom_left', 'top_right', 'center', 'diagonal'
        style: 'badge' (modern glassmorphism rounded rectangle) or 'clean' (text only with drop shadow)
        opacity: Alpha level (0-255)
    """
    base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = base_img.size
    
    # Calculate adaptive font size based on image dimensions
    font_size = max(18, min(w, h) // 22)
    font = _get_font(font_size)
    
    # Prefix watermark with clean branding icon
    display_text = f"🛡️ {text.strip()}" if not text.strip().startswith("🛡️") else text.strip()
    
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Measure text bounding box
    bbox = draw.textbbox((0, 0), display_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    padding_x = int(font_size * 0.7)
    padding_y = int(font_size * 0.4)
    badge_w = text_w + padding_x * 2
    badge_h = text_h + padding_y * 2
    margin = int(min(w, h) * 0.035)
    
    # Determine coordinate offsets
    if position == "bottom_right":
        box_x = w - badge_w - margin
        box_y = h - badge_h - margin
    elif position == "bottom_left":
        box_x = margin
        box_y = h - badge_h - margin
    elif position == "top_right":
        box_x = w - badge_w - margin
        box_y = margin
    elif position == "diagonal":
        # Full center diagonal repeating / angled watermark
        diag_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        diag_draw = ImageDraw.Draw(diag_overlay)
        diag_font = _get_font(max(24, min(w, h) // 12))
        
        diag_bbox = diag_draw.textbbox((0, 0), text, font=diag_font)
        dw = diag_bbox[2] - diag_bbox[0]
        dh = diag_bbox[3] - diag_bbox[1]
        
        # Draw translucent angled text in center
        cx = (w - dw) // 2
        cy = (h - dh) // 2
        diag_draw.text((cx, cy), text, font=diag_font, fill=(255, 255, 255, min(opacity, 120)))
        
        rotated = diag_overlay.rotate(30, resample=Image.Resampling.BICUBIC)
        composited = Image.alpha_composite(base_img, rotated).convert("RGB")
        out_buf = io.BytesIO()
        composited.save(out_buf, format="JPEG", quality=95)
        return out_buf.getvalue()
    else:  # Center
        box_x = (w - badge_w) // 2
        box_y = (h - badge_h) // 2
        
    box_x = max(0, min(box_x, w - badge_w))
    box_y = max(0, min(box_y, h - badge_h))
    
    if style == "badge":
        # Draw translucent glassmorphism badge
        radius = max(6, font_size // 3)
        draw.rounded_rectangle(
            [box_x, box_y, box_x + badge_w, box_y + badge_h],
            radius=radius,
            fill=(15, 23, 42, min(opacity, 200)),
            outline=(255, 255, 255, min(opacity + 30, 230)),
            width=2
        )
        
    # Text position inside badge
    tx = box_x + padding_x
    ty = box_y + padding_y - bbox[1]
    
    # Soft drop shadow for crisp readability
    draw.text((tx + 1, ty + 1), display_text, font=font, fill=(0, 0, 0, 180))
    # Main crisp white text
    draw.text((tx, ty), display_text, font=font, fill=(255, 255, 255, 245))
    
    # Alpha composite
    final_img = Image.alpha_composite(base_img, overlay).convert("RGB")
    
    out_buf = io.BytesIO()
    final_img.save(out_buf, format="JPEG", quality=95, optimize=True)
    return out_buf.getvalue()
