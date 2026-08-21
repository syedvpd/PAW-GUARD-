"""Single-process entrypoint: FastAPI (uvicorn) + ARQ worker together.

Lets Render's free web service tier run the background email/notification
worker without a separate (paid) Background Worker service. On startup it
launches uvicorn and the ARQ worker as concurrent asyncio tasks in the same
process; if Redis is unreachable the API still serves requests and the worker
degrades to a no-op loop.

Run with:
    uvicorn pawguard.serve:app --host 0.0.0.0 --port 10000
or directly (start command on Render):
    python -m pawguard.serve
"""

import asyncio
import sys

import uvicorn


async def _run_worker() -> None:
    from arq.worker import create_worker

    from pawguard.workers.arq_worker import WorkerSettings

    worker = create_worker(WorkerSettings)
    await worker.async_run()


async def _run_api() -> None:
    import os

    port = int(os.environ.get("PORT", "10000"))
    config = uvicorn.Config(
        "pawguard.main:app",
        host="0.0.0.0",  # noqa: S104 - must bind all interfaces on Render
        port=port,
        workers=1,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _main() -> None:
    api_task = asyncio.create_task(_run_api())
    worker_task = asyncio.create_task(_run_worker())
    done, pending = await asyncio.wait({api_task, worker_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc
        task.result()


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
