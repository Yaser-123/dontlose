from __future__ import annotations

import io
from pathlib import Path

import pytesseract
from PIL import Image
from pytesseract import TesseractNotFoundError

from app import config
from app.errors import OcrError

MAX_PAGES = 20
MAX_IMAGE_SIDE = 2500


def _configure_tesseract() -> str:
    command = config.tesseract_cmd()
    if not command:
        raise OcrError(
            "Tesseract OCR is not installed, so this image could not be read. "
            "Text-based PDFs and manual entry still work."
        )
    pytesseract.pytesseract.tesseract_cmd = command
    return command


def tesseract_status() -> dict:
    command = config.tesseract_cmd()
    if not command:
        return {"available": False, "version": None, "path": None}
    try:
        pytesseract.pytesseract.tesseract_cmd = command
        version = str(pytesseract.get_tesseract_version())
    except Exception:
        return {"available": False, "version": None, "path": command}
    return {"available": True, "version": version, "path": command}


def _prepare(image: Image.Image) -> Image.Image:
    if getattr(image, "is_animated", False):
        image.seek(0)
    rgb = image.convert("RGB")
    width, height = rgb.size
    scale = max(width, height) / MAX_IMAGE_SIDE
    if scale > 1:
        rgb = rgb.resize((int(width / scale), int(height / scale)), Image.Resampling.LANCZOS)
    return rgb


def _read_image(image: Image.Image) -> str:
    _configure_tesseract()
    try:
        return pytesseract.image_to_string(_prepare(image), config="--psm 6")
    except TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract OCR is not installed, so this image could not be read. "
            "Text-based PDFs and manual entry still work."
        ) from exc
    except OcrError:
        raise
    except Exception as exc:
        raise OcrError("The image could not be read.") from exc


def _pdf_module():
    import pymupdf

    return pymupdf


def _read_pdf(path: Path) -> tuple[str, int]:
    fitz = _pdf_module()

    try:
        document = fitz.open(path)
    except Exception as exc:
        raise OcrError("This PDF could not be opened.") from exc
    if document.needs_pass:
        document.close()
        raise OcrError("This PDF is password-protected.")
    parts: list[str] = []
    page_count = document.page_count
    try:
        for index, page in enumerate(document):
            if index >= MAX_PAGES:
                parts.append("[Stopped after 20 pages.]")
                break
            text = page.get_text("text") or ""
            if len(text.strip()) < 30:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                text = _read_image(image)
            parts.append(text)
    finally:
        document.close()
    return "\n\n".join(parts), page_count


def extract_text(path: Path) -> tuple[str, int]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, pages = _read_pdf(path)
    else:
        try:
            with Image.open(path) as image:
                text = _read_image(image)
        except OcrError:
            raise
        except Exception as exc:
            raise OcrError("This image could not be opened.") from exc
        pages = 1
    if not text or not text.strip():
        raise OcrError("No text could be read from this file.")
    cleaned = text.strip()
    if len(cleaned) > 200_000:
        cleaned = cleaned[:200_000].rstrip() + "\n\n[Text truncated.]"
    return cleaned, pages
