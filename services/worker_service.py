"""
Enterprise Background Task Worker for Smart Assistant Bot.
Runs heavy tasks (video downloads, music conversion, HD image enhancement)
in isolated background worker threads so the Telegram bot remains 100% responsive.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any

logger = logging.getLogger(__name__)

# Dedicated worker pool for heavy background tasks
_WORKER_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="AssistantWorker")

def run_in_background(func: Callable, *args, **kwargs) -> asyncio.Future:
    """Submit a synchronous heavy function to the worker thread pool non-blockingly."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_WORKER_POOL, lambda: func(*args, **kwargs))

async def execute_heavy_job(job_name: str, func: Callable, *args, **kwargs) -> Any:
    """Execute a heavy job with logging and performance timing."""
    import time
    start = time.time()
    logger.info(f"[Worker] Starting background task: {job_name}")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_WORKER_POOL, lambda: func(*args, **kwargs))
        elapsed = round(time.time() - start, 2)
        logger.info(f"[Worker] Finished background task: {job_name} in {elapsed}s")
        return result
    except Exception as e:
        logger.error(f"[Worker] Task {job_name} failed: {e}")
        raise e

def get_worker_status() -> dict:
    """Get active worker pool status."""
    return {
        "max_workers": _WORKER_POOL._max_workers,
        "is_active": True,
        "engine": "AsyncIO ThreadPool Task Runner (Enterprise Ready)",
    }
