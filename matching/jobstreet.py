from __future__ import annotations

import time

from playwright.sync_api import Locator, Page

from core.constants import JobStatus
from core.job import Job
from matching.base import Matcher


class JobStreetMatcher(Matcher):
    def is_already_applied(self, page: Page, timeout: float = 5.0) -> bool:
        locator = page.locator("#applied-date-message").get_by_text("You applied", exact=False)

        end_time = time.time() + timeout
        while time.time() < end_time:
            if locator.count() > 0:
                return True
            time.sleep(0.2)
        return False

    def verify_quick_apply(self, page: Page, job: Job) -> tuple[bool, Locator | None, JobStatus | str]:
        apply_btn = page.locator("[data-automation='job-detail-apply']").first
        try:
            apply_btn.wait_for(state="visible", timeout=8000)
        except Exception:
            return False, None, JobStatus.NOT_QUICK_APPLY

        if apply_btn.inner_text().strip().lower() != "quick apply":
            return False, None, JobStatus.NOT_QUICK_APPLY

        return True, apply_btn, JobStatus.FOUND

    def get_job_description(self, page: Page) -> str:
        try:
            selectors = (
                "[data-automation='jobAdDetails']",
                "[data-testid='jobDescription']",
                "#job-details",
                ".jobsearch-jobDescriptionText",
                ".description__text",
            )
            for selector in selectors:
                element = page.query_selector(selector)
                if element:
                    text = element.inner_text().strip()
                    if text:
                        return text[:3000]
            return page.locator("body").inner_text().strip()[:3000]
        except Exception:
            return ""
