import io
import os
import math
import logging
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

def _get_font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    """Load system font with size."""
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

def _crop_circular_avatar(avatar_img: Image.Image, size: int) -> Image.Image:
    """Crop an avatar image into an anti-aliased circle of given size."""
    avatar = avatar_img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    
    # Supersampled mask for super-smooth edges
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size * scale, size * scale), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(avatar, (0, 0), mask=mask)
    return output

def generate_welcome_banner(
    user_name: str,
    group_title: str,
    avatar_bytes: Optional[bytes] = None,
    member_count: Optional[int] = None
) -> bytes:
    """
    Generate a high-definition 1200x600 social welcome banner for new group members.
    """
    width = 1200
    height = 600
    
    # 1. Base Gradient Canvas (Midnight Navy to Deep Indigo)
    base = Image.new("RGBA", (width, height), (15, 23, 42, 255))
    draw = ImageDraw.Draw(base)
    
    for y in range(height):
        # Vertical gradient
        ratio = y / height
        r = int(15 + (30 - 15) * ratio)
        g = int(23 + (27 - 23) * ratio)
        b = int(42 + (75 - 42) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
        
    # 2. Glowing Ambient Accent Lights
    glow_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_overlay)
    
    # Top-right cyan glow
    glow_draw.ellipse([850, -150, 1350, 350], fill=(56, 189, 248, 55))
    # Bottom-left amber gold glow
    glow_draw.ellipse([-150, 350, 350, 850], fill=(245, 158, 11, 45))
    # Center ambient purple glow
    glow_draw.ellipse([450, 150, 850, 550], fill=(139, 92, 246, 35))
    
    blurred_glow = glow_overlay.filter(ImageFilter.GaussianBlur(40))
    base = Image.alpha_composite(base, blurred_glow)
    draw = ImageDraw.Draw(base)
    
    # 3. Avatar Construction
    avatar_size = 200
    avatar_x = 90
    avatar_y = (height - avatar_size) // 2
    
    if avatar_bytes:
        try:
            raw_avatar = Image.open(io.BytesIO(avatar_bytes))
            circular_avatar = _crop_circular_avatar(raw_avatar, avatar_size)
        except Exception as e:
            logger.warning(f"Failed to open avatar bytes ({e}), creating fallback monogram...")
            circular_avatar = None
    else:
        circular_avatar = None
        
    if circular_avatar is None:
        # Fallback Monogram Avatar
        monogram_img = Image.new("RGBA", (avatar_size, avatar_size), (79, 70, 229, 255))
        m_draw = ImageDraw.Draw(monogram_img)
        initial = (user_name.strip()[:1] or "?").upper()
        initial_font = _get_font(100, bold=True)
        m_bbox = m_draw.textbbox((0, 0), initial, font=initial_font)
        mw = m_bbox[2] - m_bbox[0]
        mh = m_bbox[3] - m_bbox[1]
        m_draw.text(((avatar_size - mw) // 2, (avatar_size - mh) // 2 - m_bbox[1]), initial, font=initial_font, fill=(255, 255, 255, 255))
        circular_avatar = _crop_circular_avatar(monogram_img, avatar_size)
        
    # Avatar Double Glowing Rings
    ring_radius = (avatar_size // 2) + 8
    cx = avatar_x + avatar_size // 2
    cy = avatar_y + avatar_size // 2
    
    # Outer cyan ring
    draw.ellipse([cx - ring_radius - 4, cy - ring_radius - 4, cx + ring_radius + 4, cy + ring_radius + 4], outline=(56, 189, 248, 120), width=3)
    # Inner gold ring
    draw.ellipse([cx - ring_radius, cy - ring_radius, cx + ring_radius, cy + ring_radius], outline=(245, 158, 11, 255), width=5)
    
    # Paste circular avatar
    base.paste(circular_avatar, (avatar_x, avatar_y), mask=circular_avatar)
    
    # 4. Text Typography & Badges
    content_x = avatar_x + avatar_size + 60
    
    # Welcome Tag Badge
    tag_font = _get_font(22, bold=True)
    tag_text = "🎉 WELCOME TO THE GROUP 🎉"
    tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tw = tag_bbox[2] - tag_bbox[0]
    th = tag_bbox[3] - tag_bbox[1]
    
    tag_y = 120
    draw.rounded_rectangle(
        [content_x, tag_y, content_x + tw + 28, tag_y + th + 14],
        radius=8,
        fill=(56, 189, 248, 40),
        outline=(56, 189, 248, 180),
        width=2
    )
    draw.text((content_x + 14, tag_y + 7 - tag_bbox[1]), tag_text, font=tag_font, fill=(56, 189, 248, 255))
    
    # Member Full Name
    name_font = _get_font(46, bold=True)
    display_name = user_name[:26] + "..." if len(user_name) > 26 else user_name
    name_y = tag_y + th + 36
    draw.text((content_x, name_y), display_name, font=name_font, fill=(255, 255, 255, 255))
    
    # Group Title
    group_font = _get_font(28, bold=False)
    group_name_clean = f"📍 {group_title[:32]}" + ("..." if len(group_title) > 32 else "")
    group_y = name_y + 65
    draw.text((content_x, group_y), group_name_clean, font=group_font, fill=(203, 213, 225, 230))
    
    # Subtitle / Warm Welcome
    sub_font = _get_font(24, bold=False)
    sub_text = "✨ រីករាយដែលបានស្វាគមន៍សមាជិកថ្មី! ✨"
    sub_y = group_y + 45
    draw.text((content_x, sub_y), sub_text, font=sub_font, fill=(251, 191, 36, 240))
    
    # Member Count Pill (if provided)
    if member_count:
        count_font = _get_font(20, bold=True)
        count_text = f"👤 សមាជិកទី {member_count:,}"
        c_bbox = draw.textbbox((0, 0), count_text, font=count_font)
        cw = c_bbox[2] - c_bbox[0]
        ch = c_bbox[3] - c_bbox[1]
        c_y = sub_y + 45
        draw.rounded_rectangle(
            [content_x, c_y, content_x + cw + 24, c_y + ch + 12],
            radius=6,
            fill=(30, 41, 59, 200),
            outline=(100, 116, 139, 150),
            width=1
        )
        draw.text((content_x + 12, c_y + 6 - c_bbox[1]), count_text, font=count_font, fill=(226, 232, 240, 240))
        
    # Output to JPEG Bytes
    output_buf = io.BytesIO()
    final_rgb = base.convert("RGB")
    final_rgb.save(output_buf, format="JPEG", quality=95, optimize=True)
    return output_buf.getvalue()
