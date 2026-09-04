# services/pdf_service.py
#
# Handles PDFs two ways: files the user uploads directly from their computer (saving
# them to disk and pulling out their text), and - for a saved search result that has
# no abstract - downloading a PDF from a URL the source API itself already marked as
# a free, open-access copy (see fetch_and_extract_text_from_url() below, and
# paper_service.py's get_or_fetch_source_text()). Either way, PyMuPDF is what actually
# pulls the plain text out, so Sprint 3's AI analysis has something to read.

import os
import uuid
import requests
import fitz  # this is PyMuPDF's import name - the package is installed as "PyMuPDF"

ALLOWED_EXTENSION = ".pdf"
MAX_EXTRACTED_CHARS = 200_000  # a generous cap so one huge PDF can't bloat the database

# Mirrors app.py's MAX_CONTENT_LENGTH for direct uploads - an open-access PDF fetched
# over the network shouldn't be allowed to be any more expensive to handle than one the
# user uploads themselves.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 15
DOWNLOAD_HEADERS = {"User-Agent": "ResearchLensAI-StudentProject (mailto:example@example.com)"}


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


def fetch_and_extract_text_from_url(url: str):
    """
    Download a PDF from a URL - specifically, one a source API already identified as a
    free, open-access copy (Semantic Scholar's openAccessPdf.url or OpenAlex's
    open_access.oa_url; see the two search services and paper.open_access_pdf_url) -
    and extract its text the same way extract_text_from_pdf() does for a direct
    upload. This never fetches an arbitrary web page or a paywalled publisher link;
    only a URL a source's own API already marked as freely, legally available.

    Returns (text, error). Exactly one is set - text is never an empty string (that
    counts as an error too, so callers can rely on `if text:`).
    """
    try:
        response = requests.get(
            url, headers=DOWNLOAD_HEADERS, timeout=DOWNLOAD_TIMEOUT_SECONDS, stream=True,
        )
        response.raise_for_status()

        # Read with a hard cap rather than trusting Content-Length (which can be
        # missing or wrong) - stop as soon as we've read one byte past the limit so a
        # huge file can't be downloaded in full just to get rejected afterwards.
        chunks = []
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=65536):
            total_bytes += len(chunk)
            if total_bytes > MAX_DOWNLOAD_BYTES:
                return None, "The open-access PDF for this paper is too large to fetch automatically."
            chunks.append(chunk)
        content = b"".join(chunks)
    except requests.RequestException as error:
        print(f"[pdf_service] fetching open-access PDF failed: {error}")
        return None, "Couldn't download the open-access PDF for this paper - it may no longer be available."

    try:
        text_parts = []
        with fitz.open(stream=content, filetype="pdf") as document:
            for page in document:
                text_parts.append(page.get_text())
        text = "\n".join(text_parts).strip()[:MAX_EXTRACTED_CHARS]
    except Exception as error:
        print(f"[pdf_service] extracting text from fetched PDF failed: {error}")
        return None, "Downloaded the open-access PDF, but couldn't extract readable text from it."

    if not text:
        return None, "The open-access PDF didn't contain any extractable text (it may be a scanned image)."

    return text, None