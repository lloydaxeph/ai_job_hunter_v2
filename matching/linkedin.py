from __future__ import annotations

import time

from playwright.sync_api import Locator, Page

from core.constants import JobStatus
from core.job import Job
from matching.base import Matcher


class LinkedInMatcher(Matcher):
    def is_already_applied(self, page: Page, timeout: float = 5.0) -> bool:
        old_locator = page.locator("#applied-date-message").get_by_text(
            "You applied", exact=False
        )
        new_locator = (
            page.get_by_role("heading", name="Application status")
            .locator("xpath=ancestor::div[1]/following-sibling::div")
            .get_by_text("Application submitted", exact=False)
        )

        end_time = time.time() + timeout
        while time.time() < end_time:
            if old_locator.count() > 0 or new_locator.count() > 0:
                return True
            time.sleep(0.2)
        return False

    def verify_quick_apply(self, page: Page, job: Job) -> tuple[bool, Locator | None, JobStatus | str]:
        apply_btn = page.locator("[aria-label*='Apply']").first
        try:
            apply_btn.wait_for(state="visible", timeout=8000)
        except Exception:
            return False, None, JobStatus.NOT_QUICK_APPLY

        if apply_btn.inner_text().strip().lower() != "easy apply":
            return False, None, JobStatus.NOT_QUICK_APPLY

        return True, apply_btn, JobStatus.FOUND

    def get_job_description(self, page: Page) -> str:
        try:
            more_btn = page.locator("[data-testid='expandable-text-button']").first
            if more_btn.count() > 0 and more_btn.is_visible():
                try:
                    more_btn.click(timeout=1000)
                except Exception:
                    pass

            try:
                heading = page.get_by_text("About the job", exact=True)
                heading.wait_for(timeout=3000)
                description = heading.locator(
                    "xpath=ancestor::div[1]/following-sibling::p//span[@data-testid='expandable-text-box']"
                )
                if description.count() > 0:
                    text = description.first.inner_text().strip()
                    if text:
                        return text[:3000]
            except Exception:
                pass

            try:
                description = page.locator("[data-testid='expandable-text-box']").first
                description.wait_for(timeout=3000)
                text = description.inner_text().strip()
                if text:
                    return text[:3000]
            except Exception:
                pass

            try:
                description = page.locator(
                    "//h2[normalize-space()='About the job']"
                    "/following-sibling::p"
                    "//span[@data-testid='expandable-text-box']"
                ).first
                if description.count() > 0:
                    text = description.inner_text().strip()
                    if text:
                        return text[:3000]
            except Exception:
                pass

        except Exception:
            pass

        return ""
