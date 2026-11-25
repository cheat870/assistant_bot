import io
import re
import json
import logging
import asyncio
from typing import Optional, Tuple, List, Dict, Any

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

async def _extract_document_structure(image_bytes: bytes, target_format: str = "docx") -> Dict[str, Any]:
    """Call Gemini Vision to extract structured text/tables from an image."""
    from google import genai
    from google.genai import types
    from services.ai_service import _call_gemini_api

    client = genai.Client(api_key=GEMINI_API_KEY)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    if target_format == "xlsx":
        prompt = (
            "Analyze this image very carefully. Perform high-precision OCR on any tables, invoices, receipts, lists, or structured records.\n"
            "Extract all tabular columns and rows cleanly into JSON.\n"
            "Return STRICT JSON only (no markdown, no backticks, no comments) in this exact schema:\n"
            "{\n"
            '  "title": "Sheet Title or Document Name",\n'
            '  "headers": ["Col 1", "Col 2", "Col 3", ...],\n'
            '  "rows": [\n'
            '    ["Row 1 Val 1", "Row 1 Val 2", ...],\n'
            '    ["Row 2 Val 1", "Row 2 Val 2", ...]\n'
            "  ],\n"
            '  "summary": "Brief Khmer summary of the spreadsheet contents"\n'
            "}"
        )
    else:
        prompt = (
            "Analyze this image very carefully. Perform high-precision OCR to extract all text, headings, sections, bullet points, and tables.\n"
            "Return STRICT JSON only (no markdown, no backticks, no comments) in this exact schema:\n"
            "{\n"
            '  "title": "Document Title",\n'
            '  "sections": [\n'
            "    {\n"
            '      "heading": "Section Heading (or empty)",\n'
            '      "paragraphs": ["Paragraph 1 text", "Paragraph 2 text"],\n'
            '      "bullets": ["Bullet item 1", "Bullet item 2"],\n'
            '      "table": {\n'
            '        "headers": ["Col 1", "Col 2"],\n'
            '        "rows": [["Cell 1", "Cell 2"]]\n'
            "      }\n"
            "    }\n"
            "  ],\n"
            '  "summary": "Brief Khmer summary of the document"\n'
            "}"
        )

    response = await asyncio.to_thread(
        _call_gemini_api,
        client,
        [image_part, prompt],
        "Extract document data strictly as JSON."
    )

    res_text = response.text.strip() if response and response.text else "{}"
    if res_text.startswith("```"):
        res_text = re.sub(r"^```[a-zA-Z]*\n?", "", res_text)
        res_text = re.sub(r"\n?```$", "", res_text).strip()

    try:
        return json.loads(res_text)
    except Exception as e:
        logger.warning(f"Failed to parse Gemini OCR JSON: {e}, text was: {res_text[:200]}")
        # Fallback dictionary
        return {
            "title": "ឯកសារដែលបានស្កេន (Scanned Document)",
            "headers": ["ខ្លឹមសារ (Content)"],
            "rows": [[line.strip()] for line in res_text.splitlines() if line.strip()],
            "sections": [{
                "heading": "អត្ថបទស្រង់ចេញ (Extracted Text)",
                "paragraphs": [res_text],
                "bullets": [],
                "table": None
            }],
            "summary": "បានស្រង់អត្ថបទចេញពីឯកសារដោយជោគជ័យ"
        }

async def convert_image_to_docx(image_bytes: bytes) -> Tuple[Optional[bytes], str, str]:
    """
    Convert image/document photo to formatted Microsoft Word (.docx).
    Returns: (docx_bytes, filename, summary_text)
    """
    try:
        import docx
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT

        data = await _extract_document_structure(image_bytes, target_format="docx")
        doc = docx.Document()

        # Page margins
        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # Document Title
        title_text = data.get("title", "ឯកសារដែលបានស្កេន (Scanned Document)").strip()
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_title = p_title.add_run(title_text)
        run_title.font.size = Pt(20)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(30, 58, 138)  # Deep Navy

        doc.add_paragraph()  # spacing

        sections = data.get("sections", [])
        for sec in sections:
            heading = sec.get("heading", "").strip()
            if heading:
                p_head = doc.add_paragraph()
                run_h = p_head.add_run(heading)
                run_h.font.size = Pt(14)
                run_h.font.bold = True
                run_h.font.color.rgb = RGBColor(79, 70, 229)  # Indigo
                p_head.paragraph_format.space_before = Pt(12)
                p_head.paragraph_format.space_after = Pt(4)

            # Paragraphs
            for p_text in sec.get("paragraphs", []):
                if p_text.strip():
                    p = doc.add_paragraph(p_text.strip())
                    p.paragraph_format.line_spacing = 1.15
                    p.paragraph_format.space_after = Pt(6)

            # Bullets
            for b_text in sec.get("bullets", []):
                if b_text.strip():
                    p_b = doc.add_paragraph(b_text.strip(), style="List Bullet")
                    p_b.paragraph_format.space_after = Pt(3)

            # Embedded Table
            table_data = sec.get("table")
            if table_data and isinstance(table_data, dict):
                headers = table_data.get("headers", [])
                rows = table_data.get("rows", [])
                if headers and rows:
                    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
                    t.alignment = WD_TABLE_ALIGNMENT.CENTER
                    t.style = "Table Grid"

                    # Header row
                    hdr_cells = t.rows[0].cells
                    for idx, h_text in enumerate(headers):
                        hdr_cells[idx].text = str(h_text)
                        for r in hdr_cells[idx].paragraphs[0].runs:
                            r.font.bold = True
                            r.font.color.rgb = RGBColor(255, 255, 255)

                    # Data rows
                    for r_idx, row_values in enumerate(rows):
                        row_cells = t.rows[r_idx + 1].cells
                        for c_idx, val in enumerate(row_values):
                            if c_idx < len(row_cells):
                                row_cells[c_idx].text = str(val)

                    doc.add_paragraph()  # spacing after table

        # Footer note
        p_foot = doc.add_paragraph()
        run_foot = p_foot.add_run("\n---\nបង្កើតដោយ Smart Assistant Bot OCR Master")
        run_foot.font.size = Pt(9)
        run_foot.font.italic = True
        run_foot.font.color.rgb = RGBColor(148, 163, 184)

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        file_bytes = buf.getvalue()

        clean_filename = re.sub(r"[^\w\s-]", "", title_text).strip().replace(" ", "_") or "Document"
        filename = f"{clean_filename[:30]}.docx"
        summary = data.get("summary", "បម្លែងឯកសារជា Word Document (.docx) រួចរាល់!").strip()

        return file_bytes, filename, summary

    except Exception as e:
        logger.error(f"Error converting to docx: {e}")
        return None, "document.docx", f"កំហុសក្នុងការបម្លែងជា Word៖ {str(e)[:120]}"

async def convert_image_to_xlsx(image_bytes: bytes) -> Tuple[Optional[bytes], str, str]:
    """
    Convert image/receipt/table photo to formatted Microsoft Excel (.xlsx).
    Returns: (xlsx_bytes, filename, summary_text)
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        data = await _extract_document_structure(image_bytes, target_format="xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Scanned Data"

        # Styling definitions
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")  # Navy
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        regular_font = Font(name="Calibri", size=10)
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        title_text = data.get("title", "តារាងទិន្នន័យ (Data Sheet)").strip()

        # Add Title Row
        ws.merge_cells("A1:E1")
        title_cell = ws["A1"]
        title_cell.value = title_text
        title_cell.font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
        title_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 25

        headers = data.get("headers", [])
        rows = data.get("rows", [])

        if not headers and rows:
            # Generate default headers
            headers = [f"ជួរឈរ {i+1}" for i in range(len(rows[0]))]

        # Write Headers at Row 3
        start_row = 3
        for col_idx, h_text in enumerate(headers, start=1):
            cell = ws.cell(row=start_row, column=col_idx, value=str(h_text))
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws.row_dimensions[start_row].height = 22

        # Write Rows
        for r_offset, row_values in enumerate(rows, start=1):
            curr_row = start_row + r_offset
            ws.row_dimensions[curr_row].height = 19
            for c_idx, val in enumerate(row_values, start=1):
                cell = ws.cell(row=curr_row, column=c_idx)
                # Attempt numeric conversion
                val_str = str(val).strip()
                cleaned_num = val_str.replace("$", "").replace(",", "").replace("៛", "").strip()
                try:
                    if "." in cleaned_num:
                        cell.value = float(cleaned_num)
                    else:
                        cell.value = int(cleaned_num)
                except Exception:
                    cell.value = val_str

                cell.font = regular_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

        # Auto-fit column widths
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        file_bytes = buf.getvalue()

        clean_filename = re.sub(r"[^\w\s-]", "", title_text).strip().replace(" ", "_") or "DataSheet"
        filename = f"{clean_filename[:30]}.xlsx"
        summary = data.get("summary", "បម្លែងទិន្នន័យជា Excel Spreadsheet (.xlsx) រួចរាល់!").strip()

        return file_bytes, filename, summary

    except Exception as e:
        logger.error(f"Error converting to xlsx: {e}")
        return None, "sheet.xlsx", f"កំហុសក្នុងការបម្លែងជា Excel៖ {str(e)[:120]}"
