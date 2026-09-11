"""Database repository for Invoicing & Service Fee Collection."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting
from pawguard.modules.invoice.models import Invoice, InvoiceStatus, InvoiceType


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, invoice: Invoice) -> Invoice:
        self._session.add(invoice)
        await self._session.flush()
        return invoice

    async def get_by_id(self, invoice_id: uuid.UUID) -> Invoice | None:
        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.is_deleted.is_(False))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_invoice_number(self, invoice_number: str) -> Invoice | None:
        stmt = select(Invoice).where(
            Invoice.invoice_number == invoice_number, Invoice.is_deleted.is_(False)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_payment_link_id(self, link_id: str) -> Invoice | None:
        stmt = select(Invoice).where(
            Invoice.payment_link_id == link_id, Invoice.is_deleted.is_(False)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_next_invoice_number(self) -> str:
        year = datetime.now().year
        prefix = f"INV-{year}-"
        stmt = (
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.invoice_number.like(f"{prefix}%"))
        )
        count = (await self._session.execute(stmt)).scalar_one()
        return f"{prefix}{count + 1:04d}"

    async def list_invoices_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        *,
        status: InvoiceStatus | None = None,
        invoice_type: InvoiceType | None = None,
        billed_user_id: uuid.UUID | None = None,
        search_term: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[Sequence[Invoice], int]:
        stmt = select(Invoice).where(Invoice.is_deleted.is_(False))

        if status:
            stmt = stmt.where(Invoice.status == status)
        if invoice_type:
            stmt = stmt.where(Invoice.invoice_type == invoice_type)
        if billed_user_id:
            stmt = stmt.where(Invoice.billed_user_id == billed_user_id)
        if start_date:
            stmt = stmt.where(
                Invoice.created_at >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            stmt = stmt.where(Invoice.created_at <= datetime.combine(end_date, datetime.max.time()))

        if search_term:
            pattern = f"%{search_term.strip()}%"
            stmt = stmt.where(
                or_(
                    Invoice.invoice_number.ilike(pattern),
                    Invoice.billed_org_name.ilike(pattern),
                    Invoice.recipient_email.ilike(pattern),
                    Invoice.recipient_phone.ilike(pattern),
                    Invoice.description.ilike(pattern),
                )
            )

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Apply sorting & pagination
        stmt = apply_sorting(
            stmt,
            sort,
            {
                "created_at": Invoice.created_at,
                "amount": Invoice.amount,
                "due_date": Invoice.due_date,
                "invoice_number": Invoice.invoice_number,
                "status": Invoice.status,
            },
            default_sort=Invoice.created_at.desc(),
        )
        stmt = stmt.offset(page.offset).limit(page.limit)

        result = await self._session.execute(stmt)
        return result.scalars().all(), total

    async def list_overdue_candidates(self, as_of_date: date) -> Sequence[Invoice]:
        stmt = select(Invoice).where(
            Invoice.status == InvoiceStatus.SENT,
            Invoice.due_date.is_not(None),
            Invoice.due_date < as_of_date,
            Invoice.is_deleted.is_(False),
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def update(self, invoice: Invoice) -> Invoice:
        await self._session.flush()
        return invoice
