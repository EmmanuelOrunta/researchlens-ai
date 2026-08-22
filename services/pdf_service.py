# services/pdf_service.py
#
# Handles PDFs the user uploads directly from their computer: saving the file safely
# to disk, and pulling the plain text out of it with PyMuPDF so Sprint 3's AI analysis
# has something to read later.

import os
import uuid
import fitz  # this is PyMuPDF's import name - the package is installed as "PyMuPDF"

ALLOWED_EXTENSION = ".pdf"
MAX_EXTRACTED_CHARS = 200_000  # a generous cap so one huge PDF can't bloat the database


def is_allowed_pdf(filename: str) -> bool:
    """Very basic check: does the filename end in .pdf? Good enough for a prototype."""
    return bool(filename) and filename.lower().endswith(ALLOWED_EXTENSION)


def save_uploaded_pdf(file_storage, uploads_dir: str) -> str:
    """
    Save an uploaded file to the uploads/ folder under a random name, so two people
    uploading a file called "paper.pdf" don't overwrite each other. Returns the full
    path the file was saved to.
    """
    os.makedirs(uploads_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(uploads_dir, stored_name)
    file_storage.save(file_path)
    return file_path


def extract_text_from_pdf(file_path: str) -> str:
    """
    Pull the plain text out of a PDF using PyMuPDF. Returns an empty string (rather
    than raising) if the file can't be read - a scanned/image-only PDF with no
    selectable text, for example. The upload still succeeds either way; there's just
    nothing for the AI analysis to work with later in that case.
    """
    try:
        text_parts = []
        with fitz.open(file_path) as document:
            for page in document:
                text_parts.append(page.get_text())
        return "\n".join(text_parts).strip()[:MAX_EXTRACTED_CHARS]
    except Exception:
        return ""