from __future__ import annotations

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


class LinkedInApplier(BaseApplier):
    MODAL_SELECTOR = "div.jobs-easy-apply-modal"

    def __init__(self, repository: JobRepository, cfg: AppConfig, matcher: Matcher, ai_client: AIClient | None = None):
        super().__init__(repository, cfg, matcher, ai_client)
        self.form_filler = FormFiller(
            self.ai_client,
            include_textarea=False,
            empty_select_labels=("select an option",),
        )

    def run_apply_step(self, page: Page, job: Job, resume: str, steps: int = 20, error_intervein: bool = False) -> JobStatus:
        for step in range(steps):
            page.locator('[role="dialog"]').wait_for(state="visible", timeout=10000)

            if step == 0:
                self.console.print(f"[cyan]{self.app} Using resume: {resume}[/cyan]")
                self.click_button(page, selectors=["[data-easy-apply-next-button]"])
                self.upload_resume(page, resume)
                self.write_cover_letter(page, "")
            else:
                if not self.fill_form(page, threshold=90):
                    break

            if self.click_next(page):
                page.wait_for_timeout(1000)
                continue

            if self.click_submit(page):
                page.wait_for_timeout(3000)
                status = self.submit_success(job, resume)
                self._dismiss_post_apply_modal(page)
                return status

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

    def fill_form(self, page: Page, threshold: int = 90) -> bool:
        modal = page.locator(self.MODAL_SELECTOR).first
        return self.form_filler.fill(modal, confidence_threshold=threshold)

    def write_cover_letter(self, page: Page, body: str = "") -> None:
        pass

    def upload_resume(self, page: Page, resume_path: str) -> None:
        target_resume = Path(resume_path).name
        modal = page.locator(self.MODAL_SELECTOR).first

        selected = modal.locator(
            ".jobs-document-upload-redesign-card__container--selected "
            ".jobs-document-upload-redesign-card__file-name"
        ).first
        if selected.count():
            selected_name = (selected.text_content() or "").strip()
            if selected_name == target_resume:
                return

        cards = modal.locator(".jobs-document-upload-redesign-card__container")
        for i in range(cards.count()):
            card = cards.nth(i)
            filename = (
                card.locator(".jobs-document-upload-redesign-card__file-name").text_content() or ""
            ).strip()
            if filename != target_resume:
                continue
            card.click()
            page.wait_for_timeout(500)
            return

        upload = modal.locator("input[type='file']").first
        if upload.count() == 0:
            raise RuntimeError("Resume upload input not found.")

        upload.set_input_files(str(Path(resume_path).resolve()))

        modal.locator(
            f".jobs-document-upload-redesign-card__file-name:text-is('{target_resume}')"
        ).wait_for(timeout=10000)

    def fill_known_fields(self, page: Page, cfg: AppConfig) -> None:
        personal = cfg.personal
        values = {
            "email": cfg.credentials.linkedin_email,
            "phone": personal.phone,
            "linkedin": personal.linkedin,
            "github": personal.github,
            "portfolio": personal.portfolio,
            "first": personal.first_name,
            "last": personal.last_name,
            "full_name": f"{personal.first_name} {personal.last_name}",
        }

        modal = page.locator(self.MODAL_SELECTOR).first
        for key, value in values.items():
            if not value:
                continue
            locator = modal.locator(
                f"""
                input[name*="{key}" i],
                input[id*="{key}" i],
                input[aria-label*="{key}" i]
                """
            ).first
            try:
                if locator.is_visible():
                    locator.fill(value)
            except Exception:
                continue

    def check_for_errors(self, page: Page) -> bool:
        modal = page.locator(self.MODAL_SELECTOR).first
        error_elements = modal.locator(
            ".artdeco-inline-feedback--error, [data-test-form-element-error-text]"
        )
        return error_elements.count() > 0 and error_elements.first.is_visible()

    def click_next(self, page: Page) -> bool:
        modal = page.locator(self.MODAL_SELECTOR).first
        button = modal.locator(
            "button[aria-label='Continue to next step'], button[aria-label='Review your application']"
        ).locator("visible=true").first

        if not button.count():
            return False

        button.scroll_into_view_if_needed(timeout=5000)
        button.click(timeout=5000)
        return True

    def click_submit(self, page: Page) -> bool:
        modal = page.locator(self.MODAL_SELECTOR).first
        button = modal.locator("button[aria-label='Submit application']").locator("visible=true").first

        if not button.count():
            return False

        button.scroll_into_view_if_needed(timeout=5000)
        button.click(timeout=5000)
        return True

    def _dismiss_post_apply_modal(self, page: Page) -> None:
        """Close the 'Application sent' confirmation modal, if shown."""
        try:
            dismiss_btn = page.locator(
                "button[aria-label='Dismiss'], button[aria-label='Done']"
            ).locator("visible=true").first
            if dismiss_btn.count():
                dismiss_btn.click(timeout=3000)
        except Exception:
            pass
