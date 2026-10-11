"""Stage 1: real page-level text, line boxes and tables. No OCR; scanned PDFs are reported, not fabricated."""
import io
import logging
from dataclasses import dataclass, field
from .integrity import finding, metadata_notes

log = logging.getLogger("cascade.pdf")
MIN_CHARS_PER_PAGE = 30


@dataclass
class Extraction:
    pages: list[dict] = field(default_factory=list)   # {page, text, blocks:[{bbox,text}], tables:[[row]]}
    page_count: int = 0
    metadata: dict = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    failed: bool = False
    needs_ocr: bool = False
    engine: str = ""


def _fitz():
    try:
        import pymupdf as fz
        return fz
    except ImportError:
        try:
            import fitz as fz
            return fz
        except ImportError:
            return None


def _tables(data: bytes, n_pages: int, diags: list) -> dict[int, list]:
    out: dict[int, list] = {}
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, pg in enumerate(pdf.pages[:n_pages], start=1):
                try:
                    ts = [[[("" if c is None else str(c).strip()) for c in row] for row in t] for t in pg.extract_tables()]
                    if ts: out[i] = ts
                except Exception as e:  # table extraction is best-effort
                    diags.append(finding("info", "table_extraction_failed", f"Table extraction failed on page {i}: {e}", page=i))
    except ImportError:
        diags.append(finding("info", "pdfplumber_missing", "pdfplumber not installed; table extraction skipped."))
    except Exception as e:
        diags.append(finding("info", "table_extraction_failed", f"Table extraction failed: {e}"))
    return out


def extract_pdf(data: bytes) -> Extraction:
    ex = Extraction()
    fz = _fitz()
    try:
        if fz is not None:
            ex.engine = "pymupdf"
            doc = fz.open(stream=data, filetype="pdf")
            if getattr(doc, "needs_pass", False):
                ex.failed = True
                ex.diagnostics.append(finding("error", "encrypted_pdf", "PDF is password protected; cannot extract."))
                return ex
            ex.page_count = doc.page_count; ex.metadata = dict(doc.metadata or {})
            for i, pg in enumerate(doc, start=1):
                blocks = []
                for b in pg.get_text("dict").get("blocks", []):
                    if b.get("type") != 0: continue
                    for ln in b.get("lines", []):
                        t = "".join(s.get("text", "") for s in ln.get("spans", [])).strip()
                        if t: blocks.append(dict(bbox=[round(v, 2) for v in ln["bbox"]], text=t))
                ex.pages.append(dict(page=i, text=pg.get_text("text"), blocks=blocks, tables=[]))
            doc.close()
        else:
            import pdfplumber
            ex.engine = "pdfplumber"
            ex.diagnostics.append(finding("info", "pymupdf_missing", "PyMuPDF not installed; using pdfplumber for text."))
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                ex.page_count = len(pdf.pages); ex.metadata = {k: str(v) for k, v in (pdf.metadata or {}).items()}
                for i, pg in enumerate(pdf.pages, start=1):
                    lines = pg.extract_text_lines() if hasattr(pg, "extract_text_lines") else []
                    blocks = [dict(bbox=[round(float(l["x0"]), 2), round(float(l["top"]), 2), round(float(l["x1"]), 2), round(float(l["bottom"]), 2)],
                                   text=l["text"]) for l in lines]
                    ex.pages.append(dict(page=i, text=pg.extract_text() or "", blocks=blocks, tables=[]))
    except ImportError:
        ex.failed = True
        ex.diagnostics.append(finding("error", "no_pdf_library", "Neither PyMuPDF nor pdfplumber is installed."))
        return ex
    except Exception as e:
        log.warning("PDF extraction failed: %s", e)
        ex.failed = True
        ex.diagnostics.append(finding("error", "extraction_failed", f"Could not read PDF: {e}"))
        return ex
    for i, ts in _tables(data, ex.page_count, ex.diagnostics).items():
        ex.pages[i - 1]["tables"] = ts
    chars = sum(len(p["text"].strip()) for p in ex.pages)
    if ex.page_count == 0:
        ex.failed = True; ex.diagnostics.append(finding("error", "no_pages", "PDF contains no pages."))
    elif chars < MIN_CHARS_PER_PAGE * ex.page_count:
        ex.needs_ocr = True
        ex.diagnostics.append(finding("error", "needs_ocr",
                              "Little or no extractable text; this looks like a scanned document. OCR is not enabled, so no claims were extracted."))
    ex.diagnostics += metadata_notes(ex.metadata)
    return ex
