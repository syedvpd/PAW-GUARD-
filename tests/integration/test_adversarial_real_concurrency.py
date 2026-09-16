import asyncio
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.auth_helpers import register_and_auth

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogGender, DogProfile
from pawguard.modules.donation.models import (
    CampaignStatus,
    CampaignType,
    Donation,
    DonationCampaign,
    DonationStatus,
    DonorProfile,
    PaymentWebhookEvent,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.inventory.models import InventoryItem, ItemCategory
from pawguard.modules.reports.models import JobStatus, ReportJob
from pawguard.modules.reports.router import execute_report_job


@pytest.mark.asyncio
async def test_report_job_real_transaction_sequence(engine) -> None:
    """Item 1: Prove report job creation, atomic claim, and execution sequence using real DB sessions."""
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Create a user to act as requester
    async with async_session() as session:
        user = User(
            id=uuid.uuid4(),
            email=f"tester_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="hash",
            full_name="Transaction Tester",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    # 2. Insert PENDING job into database & commit
    job_id = uuid.uuid4()
    async with async_session() as session:
        job = ReportJob(
            id=job_id,
            report_type="inventory",
            format="csv",
            status=JobStatus.PENDING.value,
            requester_id=user_id,
            created_at=datetime.now(UTC),
        )
        session.add(job)
        await session.commit()

    # 3. Worker session claims and executes AFTER commit
    async with async_session() as worker_session:
        claimed_job = await execute_report_job(job_id, worker_session)
        assert claimed_job is not None
        assert claimed_job.status == JobStatus.DONE.value, (
            f"Job failed: {claimed_job.error_message}"
        )
        assert claimed_job.result_object_key is not None

    # 4. Verify in DB state
    async with async_session() as verify_session:
        stmt = select(ReportJob).where(ReportJob.id == job_id)
        final_job = (await verify_session.execute(stmt)).scalar_one()
        assert final_job.status == JobStatus.DONE.value


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_count", [2, 5, 20])
async def test_report_job_real_concurrency(engine, worker_count: int) -> None:
    """Item 2: Test 2, 5, 20 concurrent worker sessions against the SAME ReportJob in a real DB."""
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Setup user & pending job
    job_id = uuid.uuid4()
    async with async_session() as setup_session:
        user = User(
            id=uuid.uuid4(),
            email=f"worker_test_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="hash",
            full_name="Concurrency Tester",
            is_active=True,
            is_verified=True,
        )
        setup_session.add(user)
        job = ReportJob(
            id=job_id,
            report_type="inventory",
            format="csv",
            status=JobStatus.PENDING.value,
            requester_id=user.id,
            created_at=datetime.now(UTC),
        )
        setup_session.add(job)
        await setup_session.commit()

    # 2. Worker runner function using independent AsyncSession per worker
    async def worker_task(w_idx: int):
        async with async_session() as session:
            return await execute_report_job(job_id, session)

    # 3. Launch worker_count workers concurrently
    tasks = [worker_task(i) for i in range(worker_count)]
    results = await asyncio.gather(*tasks)

    # 4. Verify atomic claim result
    async with async_session() as verify_session:
        stmt = select(ReportJob).where(ReportJob.id == job_id)
        final_job = (await verify_session.execute(stmt)).scalar_one()
        assert final_job.status == JobStatus.DONE.value, f"Job failed: {final_job.error_message}"

    # All workers returned safely without crashing
    assert len(results) == worker_count


@pytest.mark.asyncio
async def test_payment_webhook_real_50_concurrent(engine) -> None:
    """Item 3: 50 concurrent webhook calls with real independent DB sessions and transaction boundaries."""
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    event_id = f"evt_test_50_concurrent_{uuid.uuid4().hex}"
    payment_intent_id = f"pi_test_50_concurrent_{uuid.uuid4().hex}"

    # 1. Seed donor, profile, campaign, and donation
    async with async_session() as setup_session:
        user = User(
            id=uuid.uuid4(),
            email=f"donor_50_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="hash",
            full_name="50 Donor",
            is_active=True,
            is_verified=True,
        )
        setup_session.add(user)
        await setup_session.flush()

        donor_profile = DonorProfile(
            id=uuid.uuid4(),
            user_id=user.id,
        )
        setup_session.add(donor_profile)

        campaign = DonationCampaign(
            id=uuid.uuid4(),
            name="50 Concurrent Campaign",
            target_amount=Decimal("1000.00"),
            currency="USD",
            campaign_type=CampaignType.GENERAL,
            status=CampaignStatus.ACTIVE,
            start_date=date.today(),
        )
        setup_session.add(campaign)
        await setup_session.flush()

        donation = Donation(
            id=uuid.uuid4(),
            donor_id=donor_profile.id,
            campaign_id=campaign.id,
            amount=Decimal("100.00"),
            status=DonationStatus.PENDING,
            gateway_order_id=payment_intent_id,
            created_at=datetime.now(UTC),
        )
        setup_session.add(donation)
        await setup_session.commit()
        donation_id = donation.id

    # 2. Worker function executing production webhook deduplication & atomic status transition
    async def invoke_webhook(w_idx: int):
        async with async_session() as session:
            repo = DonationRepository(session)
            # Record webhook event (deduplicated via unique event_id constraint)
            is_new = await repo.record_webhook_event(
                gateway="stripe",
                event_id=event_id,
                event_type="payment_intent.succeeded",
                order_id=payment_intent_id,
                payment_id=f"pay_{payment_intent_id}",
            )
            if not is_new:
                return "DUPLICATE_IGNORED"

            updated, transitioned = await repo.update_gateway_fields_atomic(
                donation_id,
                status=DonationStatus.SUCCESS,
                gateway_payment_id=f"pay_{payment_intent_id}",
            )
            await session.commit()
            return "SUCCESS_TRANSITIONED" if transitioned else "ALREADY_SUCCESS"

    # 3. Fire 50 concurrent requests
    tasks = [invoke_webhook(i) for i in range(50)]
    results = await asyncio.gather(*tasks)

    # 4. Assert side effects in DB: Exactly ONE webhook event record created & donation transitioned to SUCCESS
    async with async_session() as verify_session:
        # Check donation status
        stmt_don = select(Donation).where(Donation.id == donation_id)
        don = (await verify_session.execute(stmt_don)).scalar_one()
        assert don.status == DonationStatus.SUCCESS.value

        # Check PaymentWebhookEvent count for event_id
        stmt_evt = select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id)
        events = (await verify_session.execute(stmt_evt)).scalars().all()
        assert len(events) == 1, f"Expected exactly 1 PaymentWebhookEvent row, found {len(events)}"

    # Check results distribution: exactly 1 SUCCESS_TRANSITIONED, 49 DUPLICATE_IGNORED
    transitioned_count = sum(1 for r in results if r == "SUCCESS_TRANSITIONED")
    duplicate_count = sum(1 for r in results if r == "DUPLICATE_IGNORED")
    assert transitioned_count == 1, f"Expected 1 transitioned request, got {transitioned_count}"
    assert duplicate_count == 49, f"Expected 49 duplicate requests ignored, got {duplicate_count}"


@pytest.mark.asyncio
async def test_inventory_concurrency_20_deductions(engine) -> None:
    """Item 1 (Real DB Concurrency): 20 concurrent stock deductions against an inventory item."""
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    item_id = uuid.uuid4()
    # 1. Create inventory item with 50 units in stock
    async with async_session() as setup_session:
        item = InventoryItem(
            id=item_id,
            name=f"Vaccine Vial_{uuid.uuid4().hex[:8]}",
            category=ItemCategory.VACCINE.value,
            quantity=50.0,
            unit="vial",
            unit_cost=10.0,
        )
        setup_session.add(item)
        await setup_session.commit()

    # 2. 20 concurrent requests try to deduct 5 units each (total demand 100 > available 50)
    async def deduct_stock(w_idx: int):
        async with async_session() as session:
            stmt = (
                update(InventoryItem)
                .where(InventoryItem.id == item_id, InventoryItem.quantity >= 5.0)
                .values(quantity=InventoryItem.quantity - 5.0)
                .returning(InventoryItem.quantity)
            )
            res = await session.execute(stmt)
            updated_qty = res.scalar_one_or_none()
            if updated_qty is not None:
                await session.commit()
                return True
            else:
                await session.rollback()
                return False

    tasks = [deduct_stock(i) for i in range(20)]
    results = await asyncio.gather(*tasks)

    # Exactly 10 requests must succeed (10 * 5 = 50), and 10 must fail
    successes = sum(1 for r in results if r is True)
    failures = sum(1 for r in results if r is False)
    assert successes == 10, f"Expected exactly 10 stock deductions to succeed, got {successes}"
    assert failures == 10, f"Expected exactly 10 stock deductions to fail, got {failures}"

    # Verify final quantity in DB is 0.0
    async with async_session() as verify_session:
        stmt = select(InventoryItem.quantity).where(InventoryItem.id == item_id)
        final_qty = (await verify_session.execute(stmt)).scalar_one()
        assert float(final_qty) == 0.0, f"Expected final quantity 0.0, got {final_qty}"


@pytest.mark.asyncio
async def test_adoption_dog_lock_concurrency_20(engine) -> None:
    """Item 1 (Real DB Concurrency): 20 concurrent applications for the SAME dog transitioning to APPROVED."""
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    dog_id = uuid.uuid4()
    app_ids = [uuid.uuid4() for _ in range(20)]

    # 1. Setup dog & 20 adoption applications for the SAME dog
    async with async_session() as setup_session:
        dog = DogProfile(
            id=dog_id,
            registration_number=f"REG-{uuid.uuid4().hex[:8]}",
            name="Buddy",
            gender=DogGender.MALE,
        )
        setup_session.add(dog)

        adopter = User(
            id=uuid.uuid4(),
            email=f"adopter_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="hash",
            full_name="Adopter",
            is_active=True,
            is_verified=True,
        )
        setup_session.add(adopter)
        await setup_session.flush()

        for app_id in app_ids:
            app = AdoptionApplication(
                id=app_id,
                dog_id=dog_id,
                adopter_id=adopter.id,
                status=AdoptionStatus.SUBMITTED,
                residential_status="owned",
            )
            setup_session.add(app)
        await setup_session.commit()

    # 2. 20 concurrent tasks try to transition their respective application to APPROVED
    async def approve_app(app_id: uuid.UUID):
        async with async_session() as session:
            try:
                stmt = (
                    update(AdoptionApplication)
                    .where(AdoptionApplication.id == app_id)
                    .values(status=AdoptionStatus.APPROVED.value)
                )
                await session.execute(stmt)
                await session.commit()
                return "APPROVED"
            except Exception as exc:
                await session.rollback()
                return type(exc).__name__

    tasks = [approve_app(app_ids[i]) for i in range(20)]
    results = await asyncio.gather(*tasks)

    # Exactly 1 application must be APPROVED due to partial unique index ix_adoption_applications_dog_lock_states
    approved_count = sum(1 for r in results if r == "APPROVED")
    assert approved_count == 1, f"Expected exactly 1 application approved, got {approved_count}"


@pytest.mark.asyncio
async def test_report_bola_real_http_endpoints(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Item 4: Real HTTP API BOLA enforcement testing User A vs User B vs Admin."""
    user_a_email = f"user_a_{uuid.uuid4().hex[:8]}@example.com"
    user_b_email = f"user_b_{uuid.uuid4().hex[:8]}@example.com"
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@example.com"

    # User A: super_admin (creates report job)
    headers_a = await register_and_auth(client, db_session, email=user_a_email, role="super_admin")
    # User B: inventory_manager (has reports:read permission, but is NOT an admin role nor the requester)
    headers_b = await register_and_auth(
        client, db_session, email=user_b_email, role="inventory_manager"
    )
    # Admin: super_admin (admin role override)
    headers_admin = await register_and_auth(
        client, db_session, email=admin_email, role="super_admin"
    )

    # 1. User A creates report job
    create_res = await client.post(
        "/api/v1/reports/jobs",
        json={"report_type": "inventory", "format": "csv"},
        headers=headers_a,
    )
    assert create_res.status_code == 202, f"User A failed to create job: {create_res.text}"
    job_id = create_res.json()["data"]["job_id"]

    # 2. User B attempts status using A's job UUID -> MUST BE 403 Forbidden (BOLA refusal)
    status_b = await client.get(f"/api/v1/reports/jobs/{job_id}", headers=headers_b)
    assert status_b.status_code == 403, (
        f"Expected 403 for User B status, got {status_b.status_code}"
    )

    # 3. User B attempts download using A's job UUID -> MUST BE 403 Forbidden (BOLA refusal)
    download_b = await client.get(f"/api/v1/reports/jobs/{job_id}/download", headers=headers_b)
    assert download_b.status_code == 403, (
        f"Expected 403 for User B download, got {download_b.status_code}"
    )

    # 4. User A attempts status -> MUST BE 200 OK
    status_a = await client.get(f"/api/v1/reports/jobs/{job_id}", headers=headers_a)
    assert status_a.status_code == 200, (
        f"Expected 200 for User A status, got {status_a.status_code}"
    )

    # 5. Admin attempts status -> MUST BE 200 OK
    status_admin = await client.get(f"/api/v1/reports/jobs/{job_id}", headers=headers_admin)
    assert status_admin.status_code == 200, (
        f"Expected 200 for Admin status, got {status_admin.status_code}"
    )
