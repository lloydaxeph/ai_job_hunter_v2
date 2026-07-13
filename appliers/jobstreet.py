from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page

from ai.openai_client import AIClient
from appliers.base import BaseApplier
from appliers.form_filler import FormFiller
from core.config import AppConfig
from core.constants import JobStatus
from core.job import Job
from db.job_repository import JobRepository
from matching.base import Matcher


class JobStreetApplier(BaseApplier):
    def __init__(self, repository: JobRepository, cfg: AppConfig, matcher: Matcher, ai_client: AIClient | None = None):
        super().__init__(repository, cfg, matcher, ai_client)
        self.form_filler = FormFiller(
            self.ai_client,
            include_textarea=True,
            empty_select_labels=(),
        )

    def run_apply_step(self, page: Page, job: Job, resume: str, steps: int = 20, error_intervein: bool = False) -> JobStatus:
        for step in range(steps):
            if step == 0:
                self.console.print(f"[cyan]{self.app} Using resume: {resume}[/cyan]")
                self.handle_aus_work_rights_popup(page)
                self.upload_resume(page, resume)
                self.write_cover_letter(page, "")
            else:
                self.fill_form(page, threshold=90)
                if self.check_for_errors(page):
                    if error_intervein:
                        self.wait_for_manual_intervention(page)
                    else:
                        break

            if self.click_button(page, selectors=[
                "[data-testid='continue-button']",
                "button:has-text('Next')",
            ]):
                page.wait_for_load_state("networkidle")
                continue

            if self.click_submit(page):
                page.wait_for_timeout(3000)
                return self.submit_success(job, resume)

            status = JobStatus.REQUIRES_MANUAL_REVIEW
            self.repository.update_status(job_id=job.job_id, status=status)
            self.console.print(
                f"[yellow]{self.app} '{job.title}' requires manual review — no submit button found.[/yellow]"
            )
            return status

        status = JobStatus.REQUIRES_MANUAL_REVIEW
        self.repository.update_status(job_id=job.job_id, status=status)
        self.console.print(
            f"[yellow]{self.app} '{job.title}' requires manual review — exceeded step limit.[/yellow]"
        )
        return status

    def handle_aus_work_rights_popup(self, page: Page, timeout: float = 3.0, poll_interval: float = 0.25) -> bool:
        """Wait briefly for the work rights popup; if found, click sponsorship-required."""
        self.console.print(f"{self.app} Waiting for work rights popup.")
        popup = page.get_by_text("Verify your work rights to continue applying", exact=False)

        end_time = time.time() + timeout
        while time.time() < end_time:
            if popup.count() > 0:
                page.get_by_role(
                    "button", name="I require sponsorship to work for a new employer"
                ).click()
                return True
            time.sleep(poll_interval)
        return False

    def fill_form(self, page: Page, threshold: int = 90) -> bool:
        form = page.locator("form").first
        return self.form_filler.fill(form, confidence_threshold=threshold)

    def write_cover_letter(self, page: Page, body: str = "") -> None:
        option = page.locator("[data-testid='coverLetter-method-none']").first
        option.wait_for(timeout=10000)

        if not body or not body.strip():
            option.check()
            page.wait_for_timeout(500)
            return

        # TODO: Implement custom cover letter.

    def upload_resume(self, page: Page, resume_path: str) -> None:
        target_resume = Path(resume_path).name
        resume_container = page.locator("[data-testid='resumeSelectInput']")
        resume_container.wait_for(timeout=10000)

        select = resume_container.locator("select[data-testid='select-input']")
        select.wait_for(timeout=10000)

        if select.count():
            options = select.locator("option")
            for i in range(options.count()):
                option = options.nth(i)
                text = (option.text_content() or "").strip()
                if not text or text == "Please select a resumé":
                    continue
                if target_resume in text:
                    value = option.get_attribute("value")
                    select.select_option(value=value)
                    page.wait_for_timeout(500)
                    return

        upload = page.locator("input[type='file']").first
        if not upload.count():
            raise RuntimeError("Resume upload input not found.")

        upload.set_input_files(str(Path(resume_path).resolve()))
        page.wait_for_timeout(1000)

        page.wait_for_function(
            """(filename) => {
                const select = document.querySelector("select[data-testid='select-input']");
                if (!select) return false;
                return Array.from(select.options).some(o => (o.textContent || '').includes(filename));
            }""",
            arg=target_resume,
            timeout=15000,
        )

        options = select.locator("option")
        for i in range(options.count()):
            option = options.nth(i)
            text = (option.text_content() or "").strip()
            if target_resume in text:
                value = option.get_attribute("value")
                select.select_option(value=value)
                page.wait_for_timeout(500)
                return

        raise RuntimeError(f"Unable to upload/select resume: {target_resume}")

    def fill_known_fields(self, page: Page, cfg: AppConfig) -> None:
        personal = cfg.personal
        values = {
            "email": cfg.credentials.jobstreet_email,
            "phone": personal.phone,
            "linkedin": personal.linkedin,
            "github": personal.github,
            "portfolio": personal.portfolio,
            "first": personal.first_name,
            "last": personal.last_name,
            "full_name": f"{personal.first_name} {personal.last_name}",
        }

        for key, value in values.items():
            if not value:
                continue
            locator = page.locator(
                f"""
                input[name*="{key}" i],
                input[id*="{key}" i],
                input[placeholder*="{key}" i]
                """
            ).first
            try:
                if locator.is_visible():
                    locator.fill(value)
            except Exception:
                continue

    def check_for_errors(self, page: Page) -> bool:
        error_panel = page.locator("#errorPanel")
        return error_panel.count() > 0 and error_panel.is_visible()

    def click_next(self, page: Page) -> bool:
        selectors = ["[data-testid='continue-button']", "button:has-text('Next')"]
        for selector in selectors:
            button = page.locator(selector).locator("visible=true").first
            if button.count():
                button.scroll_into_view_if_needed(timeout=5000)
                button.click(timeout=5000)
                return True
        return False

    def click_submit(self, page: Page) -> bool:
        button = page.locator(
            "button[type='submit'], button:has-text('Submit application')"
        ).locator("visible=true").first

        if not button.count():
            return False

        button.scroll_into_view_if_needed(timeout=5000)
        button.click(timeout=5000)
        return True
