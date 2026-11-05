import io
import logging
from typing import Optional, List
from PIL import Image
import qrcode

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

logger = logging.getLogger(__name__)

def generate_qr_code(text: str) -> io.BytesIO:
    """Generate a high-quality QR code image and return as BytesIO."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = io.BytesIO()
    bio.name = "qrcode.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def read_qr_code(image_bytes: bytes) -> Optional[str]:
    """Decode QR code or KHQR string from image bytes using OpenCV."""
    if cv2 is None or np is None:
        logger.info("OpenCV is not available; local QR decoding skipped.")
        return None
    try:
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
            
        detector = cv2.QRCodeDetector()
        data, bbox, _ = detector.detectAndDecode(img)
        if data:
            return data.strip()
            
        # Try OpenCV detectAndDecodeMulti
        res, decoded_info, _, _ = detector.detectAndDecodeMulti(img)
        if res and decoded_info:
            for item in decoded_info:
                if item:
                    return item.strip()
                    
    except Exception as e:
        logger.warning(f"Error decoding QR code: {e}")
        
    return None

def convert_images_to_pdf(images_bytes_list: List[bytes]) -> io.BytesIO:
    """Combine multiple images into a single PDF document."""
    pil_images: List[Image.Image] = []
    
    for img_bytes in images_bytes_list:
        try:
            im = Image.open(io.BytesIO(img_bytes))
            # Convert to RGB (PDF does not support RGBA / palette mode directly)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            pil_images.append(im)
        except Exception as e:
            logger.warning(f"Failed to open image for PDF: {e}")
            
    if not pil_images:
        raise ValueError("No valid images provided.")
        
    pdf_io = io.BytesIO()
    pdf_io.name = "document.pdf"
    
    first_image = pil_images[0]
    rest_images = pil_images[1:] if len(pil_images) > 1 else []
    
    first_image.save(
        pdf_io,
        format="PDF",
        save_all=True,
        append_images=rest_images,
        resolution=100.0,
    )
    pdf_io.seek(0)
    return pdf_io

def compress_image(image_bytes: bytes, quality: int = 65) -> io.BytesIO:
    """Compress image to reduce file size."""
    im = Image.open(io.BytesIO(image_bytes))
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")
    out_io = io.BytesIO()
    out_io.name = "compressed.jpg"
    im.save(out_io, format="JPEG", quality=quality, optimize=True)
    out_io.seek(0)
    return out_io
