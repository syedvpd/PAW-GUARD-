"""Public Web API contract tests: related blogs, unified lost/found, adoption filters.

These run against a real Postgres test database (see tests/conftest.py) so the
bandwidth-reduction and filtering behaviour is genuinely exercised, not mocked.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogProfile,
    DogStatus,
)
from pawguard.modules.lost_found.models import (
    FoundReport,
    LostReport,
    ReportStatus,
    Species,
)
from pawguard.modules.portal.models import BlogPost, ContentStatus


@pytest.mark.asyncio
async def test_related_blogs_excludes_source_and_body(
    client: AsyncClient, db_session: AsyncSession
):
    """Related-blogs endpoint returns published summaries, excludes the source
    and drafts, prefers same-category, and never leaks the full body."""
    suffix = uuid.uuid4().hex[:8]
    cat_health = f"Health-{suffix}"
    cat_news = f"News-{suffix}"
    source = BlogPost(
        title="Source Post",
        slug=f"source-{suffix}",
        excerpt="source excerpt",
        body="source body " * 50,
        category=cat_health,
        status=ContentStatus.PUBLISHED,
    )
    same1 = BlogPost(
        title="Same Cat 1",
        slug=f"same1-{suffix}",
        excerpt="e1",
        body="b1 " * 50,
        category=cat_health,
        status=ContentStatus.PUBLISHED,
    )
    same2 = BlogPost(
        title="Same Cat 2",
        slug=f"same2-{suffix}",
        excerpt="e2",
        body="b2 " * 50,
        category=cat_health,
        status=ContentStatus.PUBLISHED,
    )
    from datetime import UTC, datetime, timedelta

    different = BlogPost(
        title="Different Cat",
        slug=f"diff-{suffix}",
        excerpt="ed",
        body="bd " * 50,
        category=cat_news,
        status=ContentStatus.PUBLISHED,
        published_at=datetime.now(UTC) + timedelta(days=10),
    )
    draft = BlogPost(
        title="Draft",
        slug=f"draft-{suffix}",
        excerpt="edraft",
        body="bdraft",
        category=cat_health,
        status=ContentStatus.DRAFT,
    )
    for post in (source, same1, same2, different, draft):
        db_session.add(post)
    await db_session.commit()

    resp = await client.get(f"/api/v1/portal/blog/related?post_id={source.id}&limit=3")
    assert resp.status_code == 200
    payload = resp.json()
    assert "data" in payload and "meta" in payload
    data = payload["data"]
    assert len(data) == 3

    returned_ids = {str(item["id"]) for item in data}
    source_id, same1_id, same2_id, different_id, draft_id = (
        str(source.id),
        str(same1.id),
        str(same2.id),
        str(different.id),
        str(draft.id),
    )
    # Source excluded, draft excluded (not published).
    assert source_id not in returned_ids
    assert draft_id not in returned_ids
    # Same-category posts are preferred and present.
    assert same1_id in returned_ids and same2_id in returned_ids
    assert different_id in returned_ids
    # Summaries only: no body field, slug present.
    for item in data:
        assert "body" not in item
        assert "slug" in item
        assert "title" in item


@pytest.mark.asyncio
async def test_related_blogs_limit_cap(client: AsyncClient, db_session: AsyncSession):
    """The limit parameter is server-enforced (max 12)."""
    suffix = uuid.uuid4().hex[:8]
    source = BlogPost(
        title="Src",
        slug=f"src-cap-{suffix}",
        excerpt="e",
        body="b",
        category="Awareness",
        status=ContentStatus.PUBLISHED,
    )
    db_session.add(source)
    await db_session.commit()

    # Requesting above the cap is rejected outright.
    over = await client.get(f"/api/v1/portal/blog/related?post_id={source.id}&limit=100")
    assert over.status_code == 422

    # The maximum allowed limit is honoured in the pagination meta.
    max_resp = await client.get(f"/api/v1/portal/blog/related?post_id={source.id}&limit=12")
    assert max_resp.status_code == 200
    assert max_resp.json()["meta"]["page_size"] == 12


@pytest.mark.asyncio
async def test_unified_lost_found_resolves_both_types(
    client: AsyncClient, db_session: AsyncSession
):
    """GET /lost-found/reports/{id} resolves a lost OR found report, tags the
    kind, masks reporter PII for anonymous callers, and returns 404 only when
    the id matches neither table."""
    user = User(
        email="reporter-contract@example.com",
        full_name="Reporter Contract",
        hashed_password="x",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    from datetime import UTC, datetime

    lost = LostReport(
        user_id=user.id,
        species=Species.DOG,
        pet_name="Rex",
        breed="Beagle",
        color="Tan",
        location_address="Loc L",
        lost_at=datetime.now(UTC),
        status=ReportStatus.ACTIVE,
    )
    found = FoundReport(
        user_id=user.id,
        species=Species.CAT,
        breed_observed="Siamese",
        color_observed="White",
        location_address="Loc F",
        found_at=datetime.now(UTC),
        status=ReportStatus.ACTIVE,
    )
    db_session.add(lost)
    db_session.add(found)
    await db_session.commit()
    await db_session.refresh(lost)
    await db_session.refresh(found)

    lost_resp = await client.get(f"/api/v1/lost-found/reports/{lost.id}")
    assert lost_resp.status_code == 200
    lost_data = lost_resp.json()["data"]
    assert lost_data["kind"] == "lost"
    assert "report" in lost_data
    assert lost_data["report"]["id"] == str(lost.id)
    # Anonymous caller: reporter email is masked, not the raw value.
    assert lost_data["report"]["user"]["email"] != "reporter-contract@example.com"

    found_resp = await client.get(f"/api/v1/lost-found/reports/{found.id}")
    assert found_resp.status_code == 200
    found_data = found_resp.json()["data"]
    assert found_data["kind"] == "found"
    assert found_data["report"]["id"] == str(found.id)

    missing = await client.get(f"/api/v1/lost-found/reports/{uuid.uuid4()}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_adoption_age_and_weight_filtering(client: AsyncClient, db_session: AsyncSession):
    """Public /api/v1/dogs honours min/max age and weight as server-side,
    database-level filters (the Public Web age_group/size contract maps onto
    these primitives)."""
    suffix = uuid.uuid4().hex[:8]
    test_breed = f"TestBreed-{suffix}"
    young = DogProfile(
        registration_number=f"REG-Y-{suffix}",
        name="Young Dog",
        breed=test_breed,
        breed_classification=DogBreedClassification.UNKNOWN,
        gender=DogGender.UNKNOWN,
        status=DogStatus.SHELTER,
        is_adoptable=True,
        age_months=8,
        weight=5.0,
    )
    old = DogProfile(
        registration_number=f"REG-O-{suffix}",
        name="Old Dog",
        breed=test_breed,
        breed_classification=DogBreedClassification.UNKNOWN,
        gender=DogGender.UNKNOWN,
        status=DogStatus.SHELTER,
        is_adoptable=True,
        age_months=60,
        weight=30.0,
    )
    db_session.add(young)
    db_session.add(old)
    await db_session.commit()
    await db_session.refresh(young)
    await db_session.refresh(old)

    all_resp = await client.get(f"/api/v1/dogs?breed={test_breed}&page=1&page_size=50")
    assert all_resp.status_code == 200
    young_id, old_id = str(young.id), str(old.id)
    all_ids = {str(d["id"]) for d in all_resp.json()["data"]}
    assert young_id in all_ids and old_id in all_ids

    # Age filter: only the older dog remains.
    age_resp = await client.get(
        f"/api/v1/dogs?breed={test_breed}&min_age_months=24&page=1&page_size=50"
    )
    assert age_resp.status_code == 200
    age_ids = {str(d["id"]) for d in age_resp.json()["data"]}
    assert young_id not in age_ids and old_id in age_ids

    # Weight filter: only the heavier dog remains.
    weight_resp = await client.get(
        f"/api/v1/dogs?breed={test_breed}&min_weight=20&page=1&page_size=50"
    )
    assert weight_resp.status_code == 200
    weight_ids = {str(d["id"]) for d in weight_resp.json()["data"]}
    assert young_id not in weight_ids and old_id in weight_ids
