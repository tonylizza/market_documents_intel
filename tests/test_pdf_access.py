from pathlib import Path

import pytest
from pypdf import PdfWriter

from market_documents.exceptions import PdfDecryptionError, PdfExtractionError
from market_documents.services.pdf_access import is_encrypted, open_for_extraction


def _write_blank_pdf(path: Path, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as f:
        writer.write(f)


def _write_encrypted_pdf(path: Path, pages: int = 1) -> None:
    """An AES-encrypted PDF with an empty user password -- the same shape as
    the AES-encrypted SBP reports encountered in Milestone 1: opens
    transparently without a supplied password.
    """
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="", owner_password="owner-secret", algorithm="AES-256")
    with path.open("wb") as f:
        writer.write(f)


def test_is_encrypted_false_for_ordinary_pdf(tmp_path):
    path = tmp_path / "ordinary.pdf"
    _write_blank_pdf(path)
    assert is_encrypted(path) is False


def test_is_encrypted_true_for_aes_encrypted_pdf(tmp_path):
    path = tmp_path / "encrypted.pdf"
    _write_encrypted_pdf(path)
    assert is_encrypted(path) is True


def test_is_encrypted_false_for_corrupt_pdf(tmp_path):
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"not a real pdf")
    assert is_encrypted(path) is False


def test_open_for_extraction_ordinary_pdf(tmp_path):
    path = tmp_path / "ordinary.pdf"
    _write_blank_pdf(path, pages=3)
    with open_for_extraction(path) as doc:
        assert doc.page_count == 3


def test_open_for_extraction_transparently_decrypts_empty_password_aes_pdf(tmp_path):
    """Mirrors the real AES-encrypted SBP reports: no password is supplied,
    and the file opens and yields pages exactly like an ordinary PDF.
    """
    path = tmp_path / "encrypted.pdf"
    _write_encrypted_pdf(path, pages=2)
    with open_for_extraction(path) as doc:
        assert doc.needs_pass == 0
        assert doc.page_count == 2


def test_open_for_extraction_raises_extraction_error_for_corrupt_pdf(tmp_path):
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"not a real pdf")
    with pytest.raises(PdfExtractionError):
        with open_for_extraction(path):
            pass


def test_open_for_extraction_raises_extraction_error_for_missing_file(tmp_path):
    path = tmp_path / "does_not_exist.pdf"
    with pytest.raises(PdfExtractionError):
        with open_for_extraction(path):
            pass


def test_open_for_extraction_distinguishes_decryption_failure(tmp_path, monkeypatch):
    """A PDF that still needs a password after open (one we have no secret
    for) must raise PdfDecryptionError, distinct from PdfExtractionError.
    We simulate this by monkeypatching fitz.open's returned document, since
    constructing a real password-required PDF that isn't empty-password AES
    is outside pypdf's writer API.
    """
    import fitz

    path = tmp_path / "ordinary.pdf"
    _write_blank_pdf(path)

    class _FakeDoc:
        needs_pass = True
        page_count = 1

        def close(self):
            pass

    monkeypatch.setattr(fitz, "open", lambda _p: _FakeDoc())

    with pytest.raises(PdfDecryptionError):
        with open_for_extraction(path):
            pass
