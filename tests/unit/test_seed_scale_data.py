import pytest
from scripts.seed_scale_data import SCALE_PROFILES, ScaleDataGenerator, assert_production_safety


def test_scale_profiles_defined():
    expected_scales = ["test", "10k", "50k", "100k", "500k", "1m"]
    for scale in expected_scales:
        assert scale in SCALE_PROFILES
        assert SCALE_PROFILES[scale]["users"] > 0
        assert SCALE_PROFILES[scale]["dogs"] > 0
        assert SCALE_PROFILES[scale]["medical_records"] > 0


def test_production_safety_check():
    # 1. Reject production database URLs
    with pytest.raises(RuntimeError, match="contains production keyword"):
        assert_production_safety("postgresql+asyncpg://user:pass@prod-db.pawguard.com:5432/pawguard")

    with pytest.raises(RuntimeError, match="contains production keyword"):
        assert_production_safety("postgresql+asyncpg://user:pass@pawguard-rds.amazonaws.com:5432/pawguard")

    # 2. Allow local / test URLs
    assert_production_safety("postgresql+asyncpg://postgres:postgres@localhost:5432/pawguard_test")
    assert_production_safety("sqlite+aiosqlite:///:memory:")


def test_deterministic_seed_reproducibility():
    gen1 = ScaleDataGenerator(db_url="sqlite+aiosqlite:///:memory:", scale="test", seed=42)
    gen2 = ScaleDataGenerator(db_url="sqlite+aiosqlite:///:memory:", scale="test", seed=42)
    gen3 = ScaleDataGenerator(db_url="sqlite+aiosqlite:///:memory:", scale="test", seed=999)

    date1 = gen1.random_past_date()
    date2 = gen2.random_past_date()
    date3 = gen3.random_past_date()

    assert date1 == date2
    assert date1 != date3


@pytest.mark.asyncio
async def test_scale_generator_dry_run():
    gen = ScaleDataGenerator(
        db_url="sqlite+aiosqlite:///:memory:",
        scale="test",
        seed=12345,
        dry_run=True,
    )
    result = await gen.run()
    assert result["status"] == "dry_run_success"
    assert result["estimated_counts"]["users"] == 100
    assert result["estimated_counts"]["dogs"] == 30
