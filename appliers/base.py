from __future__ import annotations

import tkinter as tk
from abc import ABC, abstractmethod
from tkinter import messagebox

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from ai.openai_client import AIClient
from core.config import AppConfig
from core.constants import JobStatus
from core.job import Job
from core.logging import AppLogger
from db.job_repository import JobRepository
from matching.base import Matcher, MatchResult


class BaseApplier(ABC):
    """Template method for the Applier stage: given a job that already
    passed matching, pick a resume, click apply, and run the site-specific
    multi-step form flow. Matching (already-applied/quick-apply/scoring) is
    owned by the paired `Matcher`, not this class.
    """

    def __init__(self, repository: JobRepository, cfg: AppConfig, matcher: Matcher, ai_client: AIClient | None = None):
        self.app = "[Applier]"
        self.repository = repository
        self.cfg = cfg
        self.matcher = matcher
        self.ai_client = ai_client or AIClient(cfg)
        self.console = AppLogger.console()
        self.apply_btn: Locator | None = None

    def apply(self, page: Page, job: Job) -> JobStatus:
        try:
            self._open_job_item(page, job)

            result = self.matcher.evaluate(page, job)
            if not result.matched:
                return result.status

            self.apply_btn = result.apply_button
            self._click_apply()

            resume = result.recommended_resume or self.cfg.pick_resume(job.title)
            return self.run_apply_step(page, job, resume)

        except PlaywrightTimeoutError:
            return self._apply_timeout(job)
        except Exception as e:
            return self._apply_exception(job, e)

    def manual_apply(self, page: Page, job: Job) -> JobStatus:
        try:
            self._open_job_item(page, job)
            self._click_apply()

            if self.matcher.is_already_applied(page):
                status = JobStatus.APPLIED
                self.repository.update_status(job_id=job.job_id, status=status)
                return status

            page.wait_for_load_state("networkidle")

            resume = self.cfg.pick_resume(job.title)
            return self.run_apply_step(page, job, resume, steps=10, error_intervein=True)

        except PlaywrightTimeoutError:
            return self._apply_timeout(job)
        except Exception as e:
            return self._apply_exception(job, e)

    def _open_job_item(self, page: Page, job: Job) -> None:
        self.console.print(f"[cyan]{self.app} Opening {job.title} @ {job.company}...[/cyan]")
        page.goto(job.url, wait_until="domcontentloaded", timeout=30000)

    def _click_apply(self) -> None:
        if not self.apply_btn:
            raise RuntimeError(f"{self.app} No apply button is available to click.")
        self.apply_btn.click()

    def _apply_timeout(self, job: Job) -> JobStatus:
        self.console.print(
            f"[red]{self.app} Timed out applying to '{job.title}' @ '{job.company}'.[/red]"
        )
        status = JobStatus.FAILED
        self.repository.update_status(job_id=job.job_id, status=status)
        return status

    def _apply_exception(self, job: Job, e: Exception) -> JobStatus:
        self.console.print(f"[red]{self.app} Failed to apply to '{job.title}' @ '{job.company}': {e}[/red]")
        status = JobStatus.FAILED
        self.repository.update_status(job_id=job.job_id, status=status)
        return status

    def submit_success(self, job: Job, resume: str) -> JobStatus:
        self.console.print(f"[green]{self.app} Application submitted for '{job.title}' @ '{job.company}'.[/green]")
        status = JobStatus.APPLIED
        self.repository.update_status(job_id=job.job_id, status=status)
        self.repository.update_resume_used(job_id=job.job_id, resume_used=resume)
        return status

    def wait_for_manual_intervention(self, page: Page) -> None:
        """Pause automation until all validation errors are resolved."""
        while True:
            error_panel = page.locator("#errorPanel")
            if error_panel.count() == 0 or not error_panel.is_visible():
                self.console.print("[green]Validation errors resolved. Continuing...[/green]")
                return

            errors = error_panel.locator("li").all_inner_texts()
            self.console.print("")
            self.console.print("[red]----- Validation Errors -----[/red]")
            for i, error in enumerate(errors, start=1):
                self.console.print(f"[yellow]{i}. {error.strip()}[/yellow]")

            self._show_manual_intervention_popup()

            self.console.print("")
            self.console.print("[cyan]Please complete the form in the browser.[/cyan]")
            input("Press ENTER when you're ready to continue... ")
            page.wait_for_timeout(500)

    @staticmethod
    def _show_manual_intervention_popup() -> None:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showwarning(
            "AI Job Hunter",
            "Manual intervention required!\n\n"
            "Please complete the missing fields in the browser.\n\n"
            "When finished, close this dialog and press ENTER in the terminal.",
        )
        root.destroy()

    def click_button(self, page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            button = page.locator(selector).locator("visible=true").first
            if button.count():
                button.scroll_into_view_if_needed(timeout=5000)
                button.click(timeout=5000)
                return True
        return False

    @abstractmethod
    def upload_resume(self, page: Page, resume_path: str) -> None: ...

    @abstractmethod
    def write_cover_letter(self, page: Page, body: str = "") -> None: ...

    @abstractmethod
    def fill_known_fields(self, page: Page, cfg: AppConfig) -> None: ...

    @abstractmethod
    def fill_form(self, page: Page, threshold: int = 90) -> bool: ...

    @abstractmethod
    def click_next(self, page: Page) -> bool: ...

    @abstractmethod
    def click_submit(self, page: Page) -> bool: ...

    @abstractmethod
    def check_for_errors(self, page: Page) -> bool: ...

    @abstractmethod
    def run_apply_step(
        self, page: Page, job: Job, resume: str, steps: int = 20, error_intervein: bool = False
    ) -> JobStatus: ...
