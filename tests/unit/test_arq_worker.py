"""Tests for ARQ worker failure tracking and explicit retry configuration."""

from unittest.mock import patch

import pytest
from arq import Retry

from pawguard.core.metrics import get_metrics_snapshot
from pawguard.workers.arq_worker import WorkerSettings, _track_failures
from pawguard.workers.jobs.retry import retry_defer


async def _boom_job(ctx: dict) -> None:  # type: ignore[no-untyped-def]
    raise RuntimeError("boom")


async def _ok_job(ctx: dict) -> str:  # type: ignore[no-untyped-def]
    return "done"


async def _retry_job(ctx: dict) -> None:  # type: ignore[no-untyped-def]
    raise Retry(defer=60)


class TestTrackFailures:
    @pytest.mark.asyncio
    async def test_failing_job_re_raises(self) -> None:
        wrapped = _track_failures(_boom_job)
        with pytest.raises(RuntimeError, match="boom"):
            await wrapped({})

    @pytest.mark.asyncio
    async def test_failing_job_increments_metric(self) -> None:
        before = get_metrics_snapshot()
        wrapped = _track_failures(_boom_job)
        with pytest.raises(RuntimeError):
            await wrapped({})
        after = get_metrics_snapshot()

        counter_key = "arq_job_failed_total[job=_boom_job]"
        before_count = before["counters"].get(counter_key, 0)
        after_count = after["counters"].get(counter_key, 0)
        assert after_count == before_count + 1

    @pytest.mark.asyncio
    async def test_failing_job_logs_structured_error(self) -> None:
        wrapped = _track_failures(_boom_job)
        with (
            patch("pawguard.workers.arq_worker.logger.error") as mock_error,
            pytest.raises(RuntimeError),
        ):
            await wrapped({"job_id": "abc123", "job_try": 1})
        mock_error.assert_called_once()
        kwargs = mock_error.call_args.kwargs
        assert kwargs["job"] == "_boom_job"
        assert kwargs["job_id"] == "abc123"
        assert kwargs["job_try"] == 1
        assert kwargs["error_type"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_retry_is_not_counted_as_failure(self) -> None:
        before = get_metrics_snapshot()
        wrapped = _track_failures(_retry_job)
        with patch("pawguard.workers.arq_worker.logger.error") as mock_error, pytest.raises(Retry):
            await wrapped({"job_id": "abc123", "job_try": 2})
        mock_error.assert_not_called()
        after = get_metrics_snapshot()
        key = "arq_job_failed_total[job=_retry_job]"
        assert after["counters"].get(key, 0) == before["counters"].get(key, 0)

    @pytest.mark.asyncio
    async def test_successful_job_passthrough(self) -> None:
        wrapped = _track_failures(_ok_job)
        result = await wrapped({})
        assert result == "done"

    @pytest.mark.asyncio
    async def test_successful_job_does_not_count_failure(self) -> None:
        before = get_metrics_snapshot()
        wrapped = _track_failures(_ok_job)
        await wrapped({})
        after = get_metrics_snapshot()
        key = "arq_job_failed_total[job=_ok_job]"
        assert after["counters"].get(key, 0) == before["counters"].get(key, 0)

    def test_preserves_function_name(self) -> None:
        wrapped = _track_failures(_boom_job)
        assert wrapped.__name__ == "_boom_job"


class TestRetryDefer:
    def test_first_try_uses_base(self) -> None:
        assert retry_defer({"job_try": 1}) == 30

    def test_exponential_backoff(self) -> None:
        assert retry_defer({"job_try": 2}) == 60
        assert retry_defer({"job_try": 3}) == 120
        assert retry_defer({"job_try": 4}) == 240

    def test_caps_at_one_day(self) -> None:
        assert retry_defer({"job_try": 30}) == 24 * 60 * 60

    def test_missing_job_try_defaults_to_first(self) -> None:
        assert retry_defer({}) == 30

    def test_non_int_job_try_is_treated_as_first(self) -> None:
        assert retry_defer({"job_try": "bogus"}) == 30


class TestWorkerSettings:
    def test_max_tries_is_explicit(self) -> None:
        assert WorkerSettings.max_tries == 5

    def test_cron_jobs_have_explicit_max_tries(self) -> None:
        assert len(WorkerSettings.cron_jobs) >= 1
        for job in WorkerSettings.cron_jobs:
            assert job.max_tries == 2

    def test_functions_all_wrapped(self) -> None:
        for fn in WorkerSettings.functions:
            # Every registered function must be the wrapper (which re-raises
            # after logging), so ARQ failures are always visible.
            assert hasattr(fn, "__wrapped__")
