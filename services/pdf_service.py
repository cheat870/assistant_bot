import io
import logging
import asyncio
from typing import Dict, Any, Tuple, Optional
import pypdf
from config import GEMINI_API_KEY
from services.ai_service import _call_gemini_api, format_gemini_error

logger = logging.getLogger(__name__)

PDF_SUMMARY_SYSTEM_PROMPT = (
    "You are an expert executive document analyst and research assistant for Cambodian users. "
    "Your mission is to read and analyze PDF documents (contracts, school lessons, academic research, "
    "government reports, business proposals, and invoices) and provide an exceptionally clear, accurate, "
    "and professional summary in natural Khmer. "
    "Structure your output cleanly with bullet points, emojis, bold headings, and highlight important numbers, "
    "dates, deadlines, and responsibilities. Keep it respectful, concise, and easy to read on mobile."
)

PDF_QA_SYSTEM_PROMPT = (
    "You are an expert document assistant. Answer the user's question accurately and specifically "
    "based on the provided PDF document context. If the document does not mention the answer, politely "
    "state that the document does not contain that information. Always answer in polite Khmer unless asked otherwise."
)

def extract_pdf_info_and_text(pdf_bytes: bytes, max_pages: int = 35, max_chars: int = 60000) -> Dict[str, Any]:
    """Extract page count, metadata, and plain text from PDF bytes using pypdf."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        
        # Metadata extraction
        meta = reader.metadata or {}
        title = meta.title if meta.title else ""
        author = meta.author if meta.author else ""
        
        extracted_pages = []
        total_chars = 0
        pages_to_read = min(total_pages, max_pages)
        
        for idx in range(pages_to_read):
            page = reader.pages[idx]
            page_text = page.extract_text() or ""
            if page_text.strip():
                extracted_pages.append(f"--- [ទំព័រ {idx + 1}] ---\n{page_text.strip()}")
                total_chars += len(page_text)
            if total_chars >= max_chars:
                break
                
        full_text = "\n\n".join(extracted_pages)
        return {
            "success": True,
            "total_pages": total_pages,
            "read_pages": pages_to_read,
            "title": title,
            "author": author,
            "text": full_text,
            "has_text": len(full_text.strip()) > 50
        }
    except Exception as e:
        logger.warning(f"Error parsing PDF with pypdf: {e}")
        return {
            "success": False,
            "total_pages": 1,
            "read_pages": 0,
            "title": "",
            "author": "",
            "text": "",
            "has_text": False,
            "error": str(e)
        }

async def analyze_and_summarize_pdf(pdf_bytes: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
    """Analyze PDF using Gemini multimodal Part or extracted text fallback."""
    pdf_info = extract_pdf_info_and_text(pdf_bytes)
    total_pages = pdf_info.get("total_pages", 1)

    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            f"📄 *ឯកសារ PDF:* `{filename}`\n"
            f"📑 *ចំនួនទំព័រ:* {total_pages} ទំព័រ\n\n"
            f"⚠️ មុខងារ AI PDF Summarizer តម្រូវឱ្យមាន `GEMINI_API_KEY`។",
            pdf_info
        )

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)

    # 1. Primary Strategy: Direct Multimodal Gemini Part (Layout, charts, tables & text)
    try:
        pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        user_prompt = (
            f"Please read and thoroughly analyze this PDF document titled '{filename}'.\n"
            f"Total pages: {total_pages}.\n\n"
            f"Provide an executive summary in Khmer formatted as follows:\n"
            f"📌 *ឈ្មោះឯកសារ:* {filename}\n"
            f"📑 *ចំនួនទំព័រ:* {total_pages} ទំព័រ\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 *សេចក្តីសង្ខេបជារួម (Executive Summary)*\n"
            f"(Provide a concise 2-3 paragraph summary of what this document is about)\n\n"
            f"🎯 *ចំណុចសំខាន់ៗ & ខ្លឹមសារលម្អិត (Key Highlights)*\n"
            f"(3 to 6 bullet points highlighting the most important facts, numbers, responsibilities, or conclusions)\n\n"
            f"⚠️ *ចំណុចសំខាន់ត្រូវកត់សម្គាល់ ឬកាលបរិច្ឆេទ (Important Notice & Dates)*\n"
            f"(Any deadlines, rules, fees, or critical terms mentioned)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 _បងអាច Reply លើសារនេះ ដើម្បីសួរសំណួរលម្អិតបន្ថែមពីទំព័រណាមួយនៃឯកសារនេះបាន!_"
        )
        
        resp = await asyncio.to_thread(_call_gemini_api, client, [pdf_part, user_prompt], PDF_SUMMARY_SYSTEM_PROMPT)
        return resp.text, pdf_info

    except Exception as e_multimodal:
        logger.warning(f"Multimodal PDF failed ({e_multimodal}), attempting text fallback...")
        
        # 2. Secondary Strategy: Extracted Text Fallback via pypdf
        extracted_text = pdf_info.get("text", "")
        if extracted_text:
            try:
                user_prompt = (
                    f"Please read and analyze the extracted text from the PDF document titled '{filename}' ({total_pages} pages):\n\n"
                    f"{extracted_text[:40000]}\n\n"
                    f"Provide an executive summary in Khmer following the structured layout:\n"
                    f"📌 *ឈ្មោះឯកសារ:* {filename}\n"
                    f"📑 *ចំនួនទំព័រ:* {total_pages} ទំព័រ\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📝 *សេចក្តីសង្ខេបជារួម (Executive Summary)*\n"
                    f"🎯 *ចំណុចសំខាន់ៗ (Key Highlights)*\n"
                    f"⚠️ *ចំណុចគួរកត់សម្គាល់ (Important Notes)*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 _បងអាច Reply លើសារនេះ ដើម្បីសួរសំណួរលម្អិតបន្ថែមពីទំព័រណាមួយនៃឯកសារនេះបាន!_"
                )
                resp = await asyncio.to_thread(_call_gemini_api, client, user_prompt, PDF_SUMMARY_SYSTEM_PROMPT)
                return resp.text, pdf_info
            except Exception as e_text:
                logger.error(f"PDF text fallback also failed: {e_text}")
                return format_gemini_error(e_text), pdf_info
        else:
            return format_gemini_error(e_multimodal), pdf_info

async def answer_pdf_question(document_context: str, question: str, filename: str = "") -> str:
    """Answer a user's follow-up question regarding a previously uploaded PDF."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return "⚠️ មិនមាន GEMINI_API_KEY សម្រាប់ឆ្លើយសំណួរ PDF ឡើយ។"

    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = (
        f"You are answering questions about the PDF document titled '{filename}'.\n\n"
        f"DOCUMENT CONTENT / SUMMARY:\n"
        f"{document_context[:45000]}\n\n"
        f"USER QUESTION:\n"
        f"{question}\n\n"
        f"Please answer the user's question accurately in Khmer based solely on the document provided above."
    )
    
    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, prompt, PDF_QA_SYSTEM_PROMPT)
        return f"📑 *ចម្លើយពីឯកសារ ({filename})៖*\n\n{resp.text}"
    except Exception as e:
        logger.error(f"Answer PDF question failed: {e}")
        return format_gemini_error(e)
