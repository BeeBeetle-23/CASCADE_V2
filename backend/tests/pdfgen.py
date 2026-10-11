"""Dependency-free minimal PDF writer for tests (text lines + optional table rows drawn as text)."""
def make_pdf(pages: list[list[str]]) -> bytes:
    objs: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font_id = 3 + 2 * n
    for i, lines in enumerate(pages):
        content = "BT /F1 11 Tf 14 TL 50 740 Td " + " ".join(
            "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for l in lines) + " ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode())
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n"); offs = []
    for i, o in enumerate(objs, start=1):
        offs.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs: out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode()
    return bytes(out)


BANK = ["Alpha Tech LLC - Bank Statement", "Financial year FY2025-26 (amounts in lakh)", "Opening balance 10",
        "Total credits 100", "Internal transfers 12", "Loan proceeds 5", "Refunds 3", "Closing balance 20"]
TAX = ["Income Tax Return - Alpha Tech LLC", "Assessment Year 2026-27 FY2025-26 (amounts in lakh)", "Gross receipts 80", "Total income 12"]
PNL = ["Alpha Tech LLC - Profit and Loss Statement", "FY2025-26 (amounts in lakh)", "Gross revenue 80", "Operating expenses 50",
       "Cash available for debt service 30", "Scheduled debt service 20", "Total current assets 60", "Total current liabilities 30"]
