from __future__ import annotations

import random
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.logging import AppLogger

logger = AppLogger.logger()


def retry_on_timeout(attempts: int = 3):
    """Retry a flaky Playwright step (navigation, element waits) with exponential backoff.

    Only retries on TimeoutError — real errors (selector logic bugs, auth
    failures) should surface immediately rather than being masked by retries.
    """
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(PlaywrightTimeoutError),
        reraise=True,
    )


def jittered_sleep(delay_min: float, delay_max: float) -> None:
    """Sleep a randomized duration between applications to avoid a fixed,
    fingerprintable cadence."""
    delay = random.uniform(delay_min, delay_max) if delay_max > delay_min else delay_min
    logger.debug("Sleeping %.2fs between applications", delay)
    time.sleep(delay)
