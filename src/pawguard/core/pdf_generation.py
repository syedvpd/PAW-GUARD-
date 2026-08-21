"""PDF generation utilities for tax receipts, adoption agreements, and
volunteer service certificates using reportlab."""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_tax_receipt(
    *,
    donor_name: str,
    amount: float,
    currency: str,
    transaction_id: str,
    donation_date: datetime,
    org_name: str,
    org_address: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(org_name, styles["Title"]))
    elements.append(Paragraph(org_address, styles["Normal"]))
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph("Tax Deductible Receipt", styles["Heading1"]))
    elements.append(Spacer(1, 0.2 * inch))

    receipt_data = [
        ["Donor Name:", donor_name],
        ["Amount:", f"{currency} {amount:,.2f}"],
        ["Transaction ID:", transaction_id],
        ["Date:", donation_date.strftime("%B %d, %Y")],
    ]
    table = Table(receipt_data, colWidths=[2 * inch, 3.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(
        Paragraph(
            "This donation is tax-deductible to the extent permitted by law.",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(
        Paragraph(
            "Thank you for your generous support!",
            styles["Normal"],
        )
    )

    doc.build(elements)
    return buf.getvalue()


def generate_adoption_agreement(
    *,
    adopter_name: str,
    dog_name: str,
    dog_registration_number: str,
    dog_breed: str,
    fee_amount: float,
    org_name: str,
    org_address: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(org_name, styles["Title"]))
    elements.append(Paragraph(org_address, styles["Normal"]))
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph("Adoption Agreement", styles["Heading1"]))
    elements.append(Spacer(1, 0.2 * inch))

    agreement_data = [
        ["Adopter Name:", adopter_name],
        ["Dog Name:", dog_name],
        ["Registration Number:", dog_registration_number],
        ["Breed:", dog_breed],
        ["Adoption Fee:", f"{fee_amount:,.2f}"],
    ]
    table = Table(agreement_data, colWidths=[2 * inch, 3.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(
        Paragraph(
            "LIABILITY WAIVER: The adopter assumes all responsibility for the "
            "dog's well-being, including but not limited to veterinary care, "
            "food, shelter, and compliance with all local animal control laws. "
            "The adopting organisation makes no guarantees regarding the dog's "
            "health, temperament, or behaviour.",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(
        Paragraph(
            "Signed: ___________________________   Date: _______________",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(
        Paragraph(
            f"Print Name: {adopter_name}",
            styles["Normal"],
        )
    )

    doc.build(elements)
    return buf.getvalue()


def generate_volunteer_certificate(
    *,
    volunteer_name: str,
    total_hours: float,
    shifts_count: int,
    period_start: datetime | None,
    period_end: datetime | None,
    role_summary: str,
    org_name: str,
    org_address: str,
    issued_at: datetime,
) -> bytes:
    """Certificate of volunteer service (PRR 3.9): verified hours + shifts
    served, issued to the volunteer for the covered service period."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(org_name, styles["Title"]))
    elements.append(Paragraph(org_address, styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph("Certificate of Volunteer Service", styles["Heading1"]))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(
        Paragraph(
            "This certificate is proudly presented to",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(volunteer_name, styles["Heading2"]))
    elements.append(Spacer(1, 0.3 * inch))

    details = Table(
        [
            ["Total Service Hours", f"{total_hours:,.1f} hours"],
            ["Shifts Served", str(shifts_count)],
            [
                "Period",
                (
                    f"{period_start.strftime('%B %d, %Y')} – {period_end.strftime('%B %d, %Y')}"
                    if period_start and period_end
                    else "Ongoing"
                ),
            ],
            ["Areas of Service", role_summary or "General volunteer service"],
        ],
        colWidths=[2.5 * inch, 3 * inch],
    )
    details.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
            ]
        )
    )
    elements.append(details)
    elements.append(Spacer(1, 0.4 * inch))

    elements.append(
        Paragraph(
            "We extend our deepest gratitude for your dedication and "
            "compassion in caring for the animals in our community.",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.4 * inch))
    elements.append(
        Paragraph(
            f"Issued on {issued_at.strftime('%B %d, %Y')}",
            styles["Normal"],
        )
    )

    doc.build(elements)
    return buf.getvalue()


def generate_80g_certificate(
    *,
    donor_name: str,
    pan_number: str,
    amount: float,
    currency: str,
    donation_date: datetime,
    receipt_number: str,
    org_name: str,
    org_address: str,
    address: str | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(org_name, styles["Title"]))
    elements.append(Paragraph(org_address, styles["Normal"]))
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph("Tax Deduction Certificate u/s 80G", styles["Heading1"]))
    elements.append(Paragraph("Income Tax Act, 1961", styles["Normal"]))
    elements.append(Spacer(1, 0.2 * inch))

    cert_data = [
        ["Receipt Number:", receipt_number],
        ["Donor Name:", donor_name],
        ["PAN:", pan_number],
        ["Amount:", f"{currency} {amount:,.2f}"],
        ["Donation Date:", donation_date.strftime("%B %d, %Y")],
    ]
    if address:
        cert_data.insert(3, ["Address:", address])
    table = Table(cert_data, colWidths=[2 * inch, 3.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(
        Paragraph(
            "This is to certify that the above-mentioned donation has been received "
            "and is eligible for deduction under Section 80G of the Income Tax Act, 1961. "
            "The organisation is registered/recognized under the relevant provisions.",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(
        Paragraph(
            "This certificate is issued for the purpose of tax deduction claim by the donor.",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.4 * inch))
    elements.append(
        Paragraph(
            "Authorized Signatory: ___________________________",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(
        Paragraph(
            f"Date: {datetime.now().strftime('%B %d, %Y')}",
            styles["Normal"],
        )
    )

    doc.build(elements)
    return buf.getvalue()


def generate_finance_report_pdf(
    *,
    report_title: str,
    period_start: str,
    period_end: str,
    summary_data: dict,
    income_rows: list[dict],
    expense_rows: list[dict],
    org_name: str,
    org_address: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(org_name, styles["Title"]))
    elements.append(Paragraph(org_address, styles["Normal"]))
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph(report_title, styles["Heading1"]))
    elements.append(Paragraph(f"Period: {period_start} to {period_end}", styles["Normal"]))
    elements.append(Spacer(1, 0.2 * inch))

    summary_table_data = [
        ["Total Income:", f"{summary_data.get('total_income', 0):,.2f}"],
        ["Total Expenses:", f"{summary_data.get('total_expenses', 0):,.2f}"],
        ["Net Balance:", f"{summary_data.get('net_balance', 0):,.2f}"],
        ["Pending Transactions:", str(summary_data.get("pending_transactions", 0))],
    ]
    summary_table = Table(summary_table_data, colWidths=[2.5 * inch, 3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3 * inch))

    if income_rows:
        elements.append(Paragraph("Income Breakdown", styles["Heading2"]))
        income_table_data = [["Account", "Amount"]]
        for row in income_rows:
            income_table_data.append([row.get("account_name", ""), f"{row.get('amount', 0):,.2f}"])
        income_table = Table(income_table_data, colWidths=[3.5 * inch, 2 * inch])
        income_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                ]
            )
        )
        elements.append(income_table)
        elements.append(Spacer(1, 0.2 * inch))

    if expense_rows:
        elements.append(Paragraph("Expense Breakdown", styles["Heading2"]))
        expense_table_data = [["Account", "Amount"]]
        for row in expense_rows:
            expense_table_data.append([row.get("account_name", ""), f"{row.get('amount', 0):,.2f}"])
        expense_table = Table(expense_table_data, colWidths=[3.5 * inch, 2 * inch])
        expense_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                ]
            )
        )
        elements.append(expense_table)

    elements.append(Spacer(1, 0.3 * inch))
    elements.append(
        Paragraph(
            f"Report generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}",
            styles["Normal"],
        )
    )

    doc.build(elements)
    return buf.getvalue()
