"""PDF byte access, covering both ordinary and AES-encrypted reports.

PyMuPDF's underlying MuPDF library transparently decrypts AES-encrypted
PDFs that use an empty user password -- the case for the SBP reports
encountered in Milestone 1 -- during `fitz.open()` itself. No password
call, no temporary file, and no decrypted copy is ever created or
persisted; MuPDF never exposes decrypted bytes to this process. If a file
still requires a password after open (a real password-protected PDF this
application has no secret for), that is reported as a decryption failure,
kept distinct from a general extraction failure.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import fitz
from pypdf import PdfReader

from market_documents.exceptions import PdfDecryptionError, PdfExtractionError


def is_encrypted(local_path: Path) -> bool:
    """Report whether a PDF carries encryption, for provenance purposes only.

    Reuses the same pypdf[crypto] mechanism Milestone 1 already relies on
    for transparent AES support, rather than introducing a second
    encryption-detection implementation. This is not used to open the file
    for extraction -- see `open_for_extraction`.
    """
    try:
        reader = PdfReader(str(local_path))
    except Exception:
        return False
    return bool(reader.is_encrypted)


@contextmanager
def open_for_extraction(local_path: Path) -> Iterator[fitz.Document]:
    """Open a PDF for page-aware extraction.

    Raises `PdfDecryptionError` if the file still needs a password we do
    not have, and `PdfExtractionError` for any other reason the file
    cannot be opened or read (missing file, corrupt PDF, zero pages).
    """
    if not local_path.exists():
        raise PdfExtractionError(f"file not found: {local_path}")

    try:
        doc = fitz.open(str(local_path))
    except PdfExtractionError:
        raise
    except Exception as exc:
        raise PdfExtractionError(f"failed to open PDF {local_path}: {exc}") from exc

    try:
        if doc.needs_pass:
            raise PdfDecryptionError(
                f"PDF requires a password this application does not have: {local_path}"
            )
        if doc.page_count == 0:
            raise PdfExtractionError(f"PDF has no pages: {local_path}")
        yield doc
    finally:
        doc.close()
