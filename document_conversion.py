from io import BytesIO
from pathlib import Path

from docx import Document
import fitz
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import pytesseract


def to_editable_docx(filename: str, content: bytes) -> bytes:
    document = Document()
    document.add_heading("SIGL Correspondence", level=1)
    document.add_paragraph(f"Source document: {filename}")
    document.add_paragraph("")
    extension = Path(filename).suffix.lower()
    extracted = ""
    if extension == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
            extracted = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except PdfReadError:
            extracted = ""
        if not extracted:
            try:
                pdf = fitz.open(stream=content, filetype="pdf")
                extracted = "\n\n".join(
                    pytesseract.image_to_string(
                        Image.open(BytesIO(page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).tobytes("png")))
                    )
                    for page in pdf
                ).strip()
            except (fitz.FileDataError, pytesseract.TesseractNotFoundError, UnidentifiedImageError):
                extracted = ""
    elif extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        try:
            extracted = pytesseract.image_to_string(Image.open(BytesIO(content))).strip()
        except (pytesseract.TesseractNotFoundError, UnidentifiedImageError):
            extracted = ""
    if extracted:
        document.add_paragraph(extracted)
    else:
        document.add_paragraph(
            "This scan contains no machine-readable text. The original scan is retained "
            "for reference; OCR or manual transcription is required before editing."
        )
    output = BytesIO()
    document.save(output)
    return output.getvalue()
