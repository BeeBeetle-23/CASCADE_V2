import sys, pathlib, unittest
from decimal import Decimal as D
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent)); sys.path.insert(0, str(pathlib.Path(__file__).parent))
from app.services import text_utils as tu, integrity
from app.services.pdf_extraction import extract_pdf
from pdfgen import make_pdf, BANK, TAX, PNL


class Text(unittest.TestCase):
    def test_amounts_and_units(self):
        self.assertEqual(tu.find_amounts("Gross revenue ₹80 lakh")[0][:2], (D(80), "lakh"))
        self.assertEqual(tu.find_amounts("Total 1,00,00,000.50")[0][0], D("10000000.50"))
        self.assertEqual(tu.find_amounts("Growth 12%"), [])
        self.assertEqual(tu.to_lakh(D(8000000), "INR"), (D(80), "lakh"))
        self.assertEqual(tu.to_lakh(D(1), "crore"), (D(100), "lakh"))
        self.assertIsNone(tu.to_lakh(D(1), "furlongs"))
        self.assertEqual(tu.to_lakh(D(5), "lakh", "USD"), (D(5), "lakh"))
    def test_period_unit_class(self):
        import datetime as dt
        self.assertEqual(tu.detect_fy("Report FY 2025-26"), (dt.date(2025, 4, 1), dt.date(2026, 3, 31)))
        self.assertEqual(tu.detect_doc_unit("All amounts in lakhs"), "lakhs")
        self.assertEqual(tu.classify_document("Bank Statement. Opening balance ... Closing balance ... deposit")[0], "bank_statement")
        self.assertEqual(tu.classify_document("hello world")[0], "unknown")


class Integrity(unittest.TestCase):
    def test_total_and_duplicates(self):
        t = [["Item", "A", "Amt"], ["x", "1", "10"], ["y", "2", "20"], ["Total", "", "35"]]
        self.assertEqual([f["code"] for f in integrity.check_table(t, 1)], ["total_mismatch"])
        d = [["a", "b", "5"], ["a", "b", "5"]]
        self.assertEqual(integrity.check_table(d, 1)[0]["code"], "duplicate_rows")
        self.assertEqual(integrity.check_table([["a", "b", "5"], ["c", "d", "6"], ["Total", "", "11"]], 1), [])


class Pdf(unittest.TestCase):
    def test_extract_real_text_and_provenance(self):
        ex = extract_pdf(make_pdf([BANK]))
        self.assertFalse(ex.failed); self.assertFalse(ex.needs_ocr); self.assertEqual(ex.page_count, 1)
        self.assertIn("Total credits 100", ex.pages[0]["text"])
        self.assertTrue(any("Total credits" in b["text"] and len(b["bbox"]) == 4 for b in ex.pages[0]["blocks"]))
    def test_scanned_pdf_reported_not_fabricated(self):
        ex = extract_pdf(make_pdf([[""]]))
        self.assertTrue(ex.needs_ocr); self.assertIn("needs_ocr", [d["code"] for d in ex.diagnostics])
    def test_garbage_is_a_clean_failure(self):
        ex = extract_pdf(b"%PDF-1.4 not really"); self.assertTrue(ex.failed)

if __name__ == "__main__": unittest.main()
