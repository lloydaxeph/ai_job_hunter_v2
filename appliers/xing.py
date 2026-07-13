from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from ai.openai_client import AIClient
from appliers.base import BaseApplier
from appliers.xing_form_filler import XingFormFiller
from core.config import AppConfig
from core.constants import JobStatus
from core.job import Job
from db.job_repository import JobRepository
from matching.base import Matcher


class XingApplier(BaseApplier):
    WIZARD_SELECTOR = "div.wizard__WizardContainer-sc-16a760f3-0"

    def __init__(self, repository: JobRepository, cfg: AppConfig, matcher: Matcher, ai_client: AIClient | None = None):
        super().__init__(repository, cfg, matcher, ai_client)
        self.form_filler = XingFormFiller(self.ai_client)

    def run_apply_step(self, page: Page, job: Job, resume: str, steps: int = 20, error_intervein: bool = False) -> JobStatus:
        for step in range(steps):
            if self.click_submit(page):
                page.wait_for_timeout(3000)
                return self.submit_success(job, resume)

            wizard = page.locator(self.WIZARD_SELECTOR).first
            wizard.wait_for(state="visible", timeout=10000)

            if self._is_documents_step(wizard):
                self.console.print(f"[cyan]{self.app} Using resume: {resume}[/cyan]")
                self.upload_resume(page, resume)
            else:
                if not self.fill_form(page, threshold=90):
                    if error_intervein:
                        self.wait_for_manual_intervention(page)
                    else:
                        break

            if not self.click_next(page):
                status = JobStatus.REQUIRES_MANUAL_REVIEW
                self.repository.update_status(job_id=job.job_id, status=status)
                self.console.print(
                    f"[yellow]{self.app} '{job.title}' requires manual review — no continue button found.[/yellow]"
                )
                return status

            try:
                wizard.wait_for(state="detached", timeout=5000)
            except Exception:
                pass

            page.wait_for_timeout(1000)

        status = JobStatus.REQUIRES_MANUAL_REVIEW
        self.repository.update_status(job_id=job.job_id, status=status)
        self.console.print(
            f"[yellow]{self.app} '{job.title}' requires manual review — exceeded step limit.[/yellow]"
        )
        return status

    def _is_documents_step(self, wizard) -> bool:
        return wizard.locator("input[data-testid='upload-input-cv']").count() > 0

    def fill_form(self, page: Page, threshold: int = 90) -> bool:
        wizard = page.locator(self.WIZARD_SELECTOR).first
        return self.form_filler.fill(wizard, confidence_threshold=threshold)

    def write_cover_letter(self, page: Page, body: str = "") -> None:
        pass

    def upload_resume(self, page: Page, resume_path: str) -> None:
        wizard = page.locator(self.WIZARD_SELECTOR).first
        upload_input = wizard.locator("input[data-testid='upload-input-cv']").first
        upload_input.wait_for(state="attached", timeout=10000)

        upload_input.set_input_files(str(Path(resume_path).resolve()))
        page.wait_for_timeout(1000)

    def fill_known_fields(self, page: Page, cfg: AppConfig) -> None:
        personal = cfg.personal
        values = {
            "firstName.value": personal.first_name,
            "lastName.value": personal.last_name,
            "email.value": cfg.credentials.xing_email,
            "phone.value.phoneNumber": personal.phone,
        }

        wizard = page.locator(self.WIZARD_SELECTOR).first
        for name, value in values.items():
            if not value:
                continue
            field = wizard.locator(f"input[name='{name}']").first
            try:
                if field.count() and field.is_visible() and not (field.input_value() or "").strip():
                    field.fill(value)
            except Exception:
                continue

    def check_for_errors(self, page: Page) -> bool:
        # Not implemented for Xing yet — always reports no errors so the
        # apply flow never gets interrupted on a false positive.
        return False

    def click_next(self, page: Page) -> bool:
        wizard = page.locator(self.WIZARD_SELECTOR).first
        button = wizard.locator(
            "div.wizard-actions__Container-sc-2f425374-0 button:has-text('Continue')"
        ).locator("visible=true").first

        if not button.count():
            return False

        button.scroll_into_view_if_needed(timeout=5000)
        button.click(timeout=5000)
        return True

    def click_submit(self, page: Page) -> bool:
        button = page.locator(
            "div.wizard-review-styles__CTAWrapper-sc-f2ee0b4-8 button:has-text('Send application')"
        ).locator("visible=true").first

        if not button.count():
            return False

        button.scroll_into_view_if_needed(timeout=5000)
        button.click(timeout=5000)
        return True
