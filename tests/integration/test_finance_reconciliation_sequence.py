"""Regression tests for Cycle-1 P1/P2: finance reconciliation N+1 fix.

Previously:
- FinanceService.reconcile_donations() executed a full-table COUNT(*) of
  financial_transactions AND re-fetched the income/cash accounts inside the
  per-donation loop (O(N) extra full-table scans).
- Both reconcile_donations() and create_transaction() derived receipt numbers
  from that table-wide count, which (a) raced under concurrency against the
  UNIQUE transaction_number column and (b) duplicated the same number across
  a single reconciliation batch.

Now:
- A DB sequence (financial_transaction_seq) supplies atomic unique suffixes.
- Account lookups happen once before the batch loop.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Role, User
from pawguard.modules.donation.models import Donation, DonationStatus, DonorProfile
from pawguard.modules.finance.models import FinancialTransaction, GeneralLedgerEntry


@pytest.mark.asyncio
class TestFinanceReconciliationBatch:
    async def _staff_headers(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> dict:
        email = f"finstaff{uuid.uuid4().hex[:8]}@recon.test.com"
        payload = {
            "email": email,
            "password": "StrongP@ss99",
            "full_name": "Finance Staff",
            "phone": "+1234567890",
        }
        await client.post("/api/v1/auth/register", json=payload)
        user = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == email)
            )
        ).scalar_one()
        admin_role = (
            await db_session.execute(select(Role).where(Role.name == "super_admin"))
        ).scalar_one()
        user.roles.append(admin_role)
        user.is_verified = True
        await db_session.commit()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "StrongP@ss99"},
        )
        return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    async def _create_donations(
        self, db_session: AsyncSession, count: int
    ) -> list[Donation]:
        donor_user = User(
            email=f"donor{uuid.uuid4().hex[:8]}@recon.test.com",
            hashed_password="unused",
            full_name="Test Donor",
            is_verified=True,
        )
        db_session.add(donor_user)
        await db_session.flush()
        donor = DonorProfile(user_id=donor_user.id)
        db_session.add(donor)
        await db_session.flush()
        donations = []
        for i in range(count):
            donation = Donation(
                donor_id=donor.id,
                amount=float(100 + i),
                currency="USD",
                donation_type="one_time",
                status=DonationStatus.SUCCESS,
            )
            db_session.add(donation)
            donations.append(donation)
        await db_session.commit()
        return donations

    async def test_reconcile_batch_creates_unique_receipts(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._staff_headers(client, db_session)
        await client.post(
            "/api/v1/finance/accounts",
            json={
                "account_code": "4000",
                "account_name": "Donation Income",
                "account_type": "income",
                "category": "donation_income",
            },
            headers=headers,
        )
        await client.post(
            "/api/v1/finance/accounts",
            json={
                "account_code": "1010",
                "account_name": "Bank",
                "account_type": "asset",
                "category": "bank",
            },
            headers=headers,
        )
        donations = await self._create_donations(db_session, 3)

        resp = await client.post(
            "/api/v1/finance/reconcile/donations", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["reconciled"] == 3

        rows = (
            await db_session.execute(
                select(FinancialTransaction)
                .where(
                    FinancialTransaction.donation_id.in_(
                        [d.id for d in donations]
                    )
                )
                .order_by(FinancialTransaction.transaction_number)
            )
        ).scalars().all()
        assert len(rows) == 3
        numbers = [t.transaction_number for t in rows]
        assert len(set(numbers)) == 3
        assert all(n.startswith(f"DR-{datetime.now(UTC):%Y%m%d}-") for n in numbers)

        for tx in rows:
            entries = (
                await db_session.execute(
                    select(GeneralLedgerEntry).where(
                        GeneralLedgerEntry.transaction_id == tx.id
                    )
                )
            ).scalars().all()
            assert len(entries) == 2
            assert entries[0].debit_amount == tx.amount
            assert entries[1].credit_amount == tx.amount

    async def test_api_transaction_numbers_unique_and_prefix_ok(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await self._staff_headers(client, db_session)
        debit = await client.post(
            "/api/v1/finance/accounts",
            json={
                "account_code": "5000",
                "account_name": "Expense A",
                "account_type": "expense",
                "category": "supplies_expense",
            },
            headers=headers,
        )
        credit = await client.post(
            "/api/v1/finance/accounts",
            json={
                "account_code": "1011",
                "account_name": "Bank",
                "account_type": "asset",
                "category": "bank",
            },
            headers=headers,
        )
        debit_id = debit.json()["data"]["id"]
        credit_id = credit.json()["data"]["id"]

        created = []
        for _ in range(3):
            resp = await client.post(
                "/api/v1/finance/transactions",
                json={
                    "transaction_type": "expense",
                    "transaction_date": "2026-07-30",
                    "amount": 50.00,
                    "debit_account_id": debit_id,
                    "credit_account_id": credit_id,
                    "description": "Sequence test",
                },
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
            created.append(resp.json()["data"])

        numbers = [t["transaction_number"] for t in created]
        assert len(set(numbers)) == 3
        assert all(n.startswith("TXN-") for n in numbers)
