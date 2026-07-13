from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from playwright.sync_api import Locator, Page

from ai.openai_client import AIClient
from core.config import AppConfig
from core.constants import JobStatus
from core.job import Job
from core.logging import AppLogger
from db.job_repository import JobRepository


@dataclass
class MatchResult:
    """Outcome of evaluating a job. `matched=True` means the Applier should run."""

    matched: bool
    status: JobStatus
    apply_button: Locator | None = None
    recommended_resume: str | None = None


class Matcher(ABC):
    """Template method for the Scraper -> Matcher -> Applier pipeline.

    Already-applied checks, quick-apply verification, and description
    scraping are site-specific DOM concerns (abstract hooks below). AI
    scoring and the score-threshold gate are identical for every site and
    live once, here.
    """

    def __init__(self, repository: JobRepository, cfg: AppConfig, ai_client: AIClient | None = None):
        self.repository = repository
        self.cfg = cfg
        self.ai_client = ai_client or AIClient(cfg)
        self.score_threshold = cfg.ai.score_threshold
        self.console = AppLogger.console()
        self.app = "[Matcher]"

    def evaluate(self, page: Page, job: Job) -> MatchResult:
        """Run the full matching pipeline for a single, already-opened job page."""
        if self.is_already_applied(page):
            status = JobStatus.APPLIED
            self.console.print(f"[yellow]{self.app} Already applied — skipping '{job.title}' @ '{job.company}'.[/yellow]")
            self.repository.update_status(job_id=job.job_id, status=status)
            return MatchResult(matched=False, status=status)

        is_quick_apply, apply_button, status = self.verify_quick_apply(page, job)
        if not is_quick_apply:
            self.console.print(
                f"[yellow]{self.app} Not eligible for Quick Apply — skipping '{job.title}' (status: {status}).[/yellow]"
            )
            self.repository.update_status(job_id=job.job_id, status=status)
            return MatchResult(matched=False, status=status)

        description = self.get_job_description(page)
        if not description:
            self.console.print(f"[red]{self.app} Failed to retrieve job description for '{job.title}'.[/red]")
            status = JobStatus.FAILED
            self.repository.update_status(job_id=job.job_id, status=status)
            return MatchResult(matched=False, status=status)

        job.description = description
        self.repository.update_description(job_id=job.job_id, description=description)

        duplicate = self.repository.find_scored_duplicate(job.company, job.title)
        if duplicate is not None:
            job.score = duplicate.score
            self.console.print(
                f"[cyan]{self.app} Reusing cached score ({job.score}) for repost: "
                f"'{job.title}' @ '{job.company}'.[/cyan]"
            )
        else:
            ai_result = self.ai_client.score_job(job.to_dict())
            job.score = ai_result.get("score", 0)

        self.repository.update_score(job_id=job.job_id, score=job.score)

        if job.score < self.score_threshold:
            self.console.print(
                f"[red]{self.app} DID NOT MATCH — '{job.title}' @ '{job.company}' "
                f"scored {job.score}/10 (threshold: {self.score_threshold}).[/red]"
            )
            status = JobStatus.DID_NOT_MATCH
            self.repository.update_status(job_id=job.job_id, status=status)
            return MatchResult(matched=False, status=status)

        self.console.print(
            f"[green]{self.app} MATCHED — '{job.title}' @ '{job.company}' "
            f"scored {job.score}/10 (threshold: {self.score_threshold}).[/green]"
        )

        recommended_resume = None
        if duplicate is None:
            recommended_resume = ai_result.get("recommended_resume")

        return MatchResult(
            matched=True,
            status=JobStatus.FOUND,
            apply_button=apply_button,
            recommended_resume=recommended_resume,
        )

    @abstractmethod
    def is_already_applied(self, page: Page) -> bool:
        """Site-specific DOM check for an existing application."""

    @abstractmethod
    def verify_quick_apply(self, page: Page, job: Job) -> tuple[bool, Locator | None, JobStatus | str]:
        """Site-specific check that the job supports one-click/quick apply.

        Returns (is_quick_apply, apply_button_locator, status_if_not_quick_apply).
        """

    @abstractmethod
    def get_job_description(self, page: Page) -> str:
        """Site-specific scrape of the full job description text."""
