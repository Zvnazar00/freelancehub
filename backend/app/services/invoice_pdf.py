"""Server-side invoice PDF (ADR-10, revised): fpdf2 is pure Python, so the API image needs no system
libraries (WeasyPrint would need Pango/Cairo). Inter is embedded for full Latin + Cyrillic coverage.

The PDF is rendered from the same serialized InvoiceOut the API returns, so the document can never show
numbers that differ from the JSON. Amounts are printed with the ISO currency code (no FX, no symbols that
a font might miss). PDFs are rendered on request and not stored; issued invoices are immutable, so the
output for a given invoice version is deterministic apart from the creation timestamp.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos
from fpdf.fonts import FontFace

from app.schemas.invoices import InvoiceOut

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

INK = (24, 26, 33)
MUTED = (110, 116, 132)
ACCENT = (108, 92, 231)
RULE = (226, 228, 235)
ZEBRA = (247, 247, 251)

STATUS_LABEL = {"draft": "DRAFT", "sent": "DUE", "paid": "PAID", "void": "VOID"}


def money(value: Decimal, currency: str) -> str:
    return f"{value:,.2f} {currency}"


def hours(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}"


def long_date(value: date) -> str:
    return value.strftime("%d %b %Y")


class _Doc(FPDF):
    def __init__(self, invoice: InvoiceOut) -> None:
        super().__init__(orientation="portrait", unit="mm", format="A4")
        self.invoice = invoice
        self.add_font("Inter", "", FONTS / "Inter_400Regular.ttf")
        self.add_font("Inter", "B", FONTS / "Inter_600SemiBold.ttf")
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=22)
        title = f"Invoice {invoice.number}" if invoice.number else "Draft invoice"
        self.set_title(title)
        self.set_author(invoice.from_name or "")
        self.set_creator("FreelanceHub")

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Inter", "", 8)
        self.set_text_color(*MUTED)
        label = self.invoice.number or "Draft"
        self.cell(0, 5, f"{label} · page {self.page_no()}/{{nb}}", align=Align.R)


def render_invoice_pdf(invoice: InvoiceOut) -> bytes:
    pdf = _Doc(invoice)
    pdf.alias_nb_pages()
    pdf.add_page()
    width = pdf.epw

    # ---- header
    pdf.set_text_color(*ACCENT)
    pdf.set_font("Inter", "B", 22)
    pdf.cell(width / 2, 10, "INVOICE")
    pdf.set_font("Inter", "B", 11)
    status = STATUS_LABEL[invoice.status.value]
    if invoice.is_overdue:
        status = "OVERDUE"
    pdf.cell(width / 2, 10, status, align=Align.R, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*INK)
    pdf.set_font("Inter", "", 11)
    pdf.cell(0, 6, invoice.number or "Draft — not issued yet", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    # ---- parties and dates
    top = pdf.get_y()
    col = width / 3
    _block(pdf, pdf.l_margin, top, col, "FROM", [invoice.from_name or "", invoice.from_email or ""])
    bill = invoice.bill_to
    _block(pdf, pdf.l_margin + col, top, col, "BILL TO", [bill.name, bill.company or "", bill.email or ""])
    _block(
        pdf,
        pdf.l_margin + 2 * col,
        top,
        col,
        "DETAILS",
        [
            f"Issued: {long_date(invoice.issue_date)}",
            f"Due: {long_date(invoice.due_date)}",
            f"Currency: {invoice.currency}",
        ],
        emphasize_first=False,
    )
    pdf.set_y(top + 26)

    # ---- lines
    pdf.set_font("Inter", "", 9)
    pdf.set_draw_color(*RULE)
    header_style = FontFace(family="Inter", emphasis="BOLD", color=MUTED, fill_color=(255, 255, 255))
    with pdf.table(
        col_widths=(22, 82, 18, 26, 26),
        text_align=(Align.L, Align.L, Align.R, Align.R, Align.R),
        headings_style=header_style,
        line_height=5.5,
        padding=(1.6, 1.5),
        borders_layout="HORIZONTAL_LINES",
        cell_fill_color=ZEBRA,
        cell_fill_mode="ROWS",
        first_row_as_headings=True,
    ) as table:
        table.row(("Date", "Description", "Hours / Qty", "Rate", "Amount"))
        for line in invoice.items:
            is_time = line.duration_seconds is not None
            table.row(
                (
                    long_date(line.service_date) if line.service_date else "",
                    line.description,
                    hours(line.duration_seconds or 0) if is_time else f"{line.quantity.normalize():f}",
                    f"{line.unit_price:,.2f}",
                    f"{line.amount:,.2f}",
                )
            )

    # ---- totals
    pdf.ln(4)
    rows: list[tuple[str, str, bool]] = [("Subtotal", money(invoice.subtotal, invoice.currency), False)]
    if invoice.tax_rate > 0:
        rows.append((f"Tax ({invoice.tax_rate.normalize():f}%)", money(invoice.tax_amount, invoice.currency), False))
    rows.append(("Total", money(invoice.total, invoice.currency), True))
    if invoice.amount_paid > 0:
        rows.append(("Paid", money(invoice.amount_paid, invoice.currency), False))
    if invoice.status.value in ("sent", "paid"):
        rows.append(("Amount due", money(invoice.amount_due, invoice.currency), True))
    label_w, value_w = 40.0, 40.0
    for label, value, strong in rows:
        pdf.set_x(pdf.l_margin + width - label_w - value_w)
        pdf.set_font("Inter", "B" if strong else "", 11 if strong else 10)
        pdf.set_text_color(*(INK if strong else MUTED))
        pdf.cell(label_w, 7, label, align=Align.R)
        pdf.set_text_color(*INK)
        pdf.cell(value_w, 7, value, align=Align.R, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---- payments and notes
    if invoice.payments:
        pdf.ln(4)
        _heading(pdf, "PAYMENTS")
        pdf.set_font("Inter", "", 9)
        for p in invoice.payments:
            method = p.method.value.replace("_", " ")
            pdf.cell(0, 5, f"{long_date(p.paid_on)} · {method} · {money(p.amount, invoice.currency)}")
            pdf.ln(5)
    if invoice.notes:
        pdf.ln(4)
        _heading(pdf, "NOTES")
        pdf.set_font("Inter", "", 9)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 5, invoice.notes, align=Align.L)

    return bytes(pdf.output())


def _heading(pdf: FPDF, text: str) -> None:
    pdf.set_font("Inter", "B", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*INK)


def _block(
    pdf: FPDF, x: float, y: float, w: float, title: str, lines: list[str], *, emphasize_first: bool = True
) -> None:
    pdf.set_xy(x, y)
    pdf.set_font("Inter", "B", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(w, 5, title, new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_text_color(*INK)
    for i, line in enumerate(x for x in lines if x):
        strong = emphasize_first and i == 0
        pdf.set_font("Inter", "B" if strong else "", 10 if strong else 9)
        pdf.set_x(x)
        pdf.cell(w - 4, 5, _fit(pdf, line, w - 4), new_x=XPos.LEFT, new_y=YPos.NEXT)


def _fit(pdf: FPDF, text: str, width: float) -> str:
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "…") > width:
        text = text[:-1]
    return text + "…"
