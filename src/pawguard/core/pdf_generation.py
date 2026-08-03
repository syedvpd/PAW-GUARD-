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
        buf, pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
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
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
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
        buf, pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
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
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
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
        buf, pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
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
            ["Period", (
                f"{period_start.strftime('%B %d, %Y')} – "
                f"{period_end.strftime('%B %d, %Y')}"
                if period_start and period_end else "Ongoing"
            )],
            ["Areas of Service", role_summary or "General volunteer service"],
        ],
        colWidths=[2.5 * inch, 3 * inch],
    )
    details.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
    ]))
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
