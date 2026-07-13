from __future__ import annotations

from playwright.sync_api import Page

from ai.openai_client import AIClient
from core.config import ApplyConfig, AppConfig
from core.constants import JobAgentMode, JobStatus
from core.job import Job
from core.logging import AppLogger
from db.job_repository import JobRepository
from orchestration.site_registry import SiteRegistry
from reliability.retry import jittered_sleep


class JobApplicationService:
    """Runs the Matcher -> Applier pipeline over a batch of jobs."""

    def __init__(self, apply_cfg: ApplyConfig, cfg: AppConfig, repository: JobRepository, dry_run: bool = False):
        self.apply_cfg = apply_cfg
        self.cfg = cfg
        self.repository = repository
        self.dry_run = dry_run
        self.console = AppLogger.console()
        self.logger = AppLogger.logger()
        self._ai_client: AIClient | None = None

    def _shared_ai_client(self) -> AIClient:
        if self._ai_client is None:
            self._ai_client = AIClient(self.cfg)
        return self._ai_client

    def _build_applier(self, site: str):
        site_classes = SiteRegistry.get(site)
        if site_classes is None:
            return None

        ai_client = self._shared_ai_client()
        matcher = site_classes.matcher(self.repository, self.cfg, ai_client)
        return site_classes.applier(self.repository, self.cfg, matcher, ai_client)

    def run(self, page: Page, jobs: list[Job], mode: JobAgentMode) -> int:
        jobs_applied = 0
        delay_min, delay_max = self.apply_cfg.jitter_bounds()

        for i, job in enumerate(jobs):
            self.console.print(f"[bold]--- Job {i + 1} of {len(jobs)} ---[/bold]")
            applier = self._build_applier(job.site)
            if applier is None:
                self.logger.warning("No applier registered for '%s'. Skipping '%s'.", job.site, job.title)
                self.repository.update_status(job_id=job.job_id, status=JobStatus.FAILED)
                continue

            if self.dry_run:
                status = applier.matcher.evaluate(page, job).status
                self.console.print(f"[yellow][Dry Run] Matching result for '{job.title}': {status}[/yellow]")
            elif mode == JobAgentMode.MANUAL_REVIEW:
                status = applier.manual_apply(page, job)
            else:
                status = applier.apply(page, job)

            if status == JobStatus.APPLIED:
                jobs_applied += 1
                self.console.print(f"[bold green]Applications submitted so far: {jobs_applied}[/bold green]")

            jittered_sleep(delay_min, delay_max)

        return jobs_applied
