from __future__ import annotations

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from core.config import AppConfig
from core.constants import JobAgentMode, JobStatus
from core.job import Job
from core.logging import AppLogger
from db.database import Database
from db.job_repository import JobRepository
from filtering.job_filter import JobFilter
from orchestration.application_service import JobApplicationService
from orchestration.scraping_service import JobScrapingService
from orchestration.site_registry import SiteRegistry


class JobHunterApp:
    """Thin orchestrator — wires the helper services and runs the pipeline."""

    def __init__(self, cfg: AppConfig, dry_run: bool = False) -> None:
        self.cfg = cfg
        self.dry_run = dry_run
        self.console = AppLogger.console()

        job_filter = JobFilter(banned_companies=cfg.banned_companies, avoid_titles=cfg.banned_titles)
        self.database = Database()
        self.repository = JobRepository(self.database.connection)
        self.scraping_service = JobScrapingService(cfg.search, job_filter, self.repository)
        self.application_service = JobApplicationService(cfg.apply, cfg, self.repository, dry_run=dry_run)

    def _get_jobs_to_apply(self, jobs: list[Job]) -> list[Job]:
        if self.cfg.apply.auto_apply:
            self.console.print("[cyan][Agent] Auto-apply is enabled.[/cyan]")
            return jobs

        self.console.print("[yellow][Agent] Manual application review is not yet implemented.[/yellow]")
        return []

    def _create_session(self, pw, site: str) -> tuple:
        site_classes = SiteRegistry.get(site)
        if site_classes is None:
            raise ValueError(f"No session manager registered for site '{site}'")

        session_manager = site_classes.session_manager()
        browser = pw.chromium.launch(headless=self.cfg.apply.headless)
        context = session_manager.create_context(browser=browser)
        return session_manager, browser, context

    def default_apply_mode(self, page: Page, site: str) -> None:
        self.console.print("[bold cyan][Agent] Quick Apply mode[/bold cyan]")
        jobs = self.scraping_service.scrape(page, site)
        if not jobs:
            self.console.print("[yellow][Agent] No jobs found.[/yellow]")
            return

        jobs_to_apply = self._get_jobs_to_apply(jobs)
        if not jobs_to_apply:
            self.console.print("[yellow][Agent] No jobs selected for application.[/yellow]")
            return

        self.console.print(f"[cyan][Agent] Applying to {len(jobs_to_apply)} job(s)...[/cyan]")
        total_applied = self.application_service.run(page, jobs_to_apply, mode=JobAgentMode.QUICK_APPLY)
        self.console.print(
            f"[green][Agent] Applied to {total_applied} of {len(jobs)} job(s) found on {site}.[/green]"
        )

    def status_based_run(self, page: Page, site: str, mode: JobAgentMode, status: JobStatus) -> None:
        self.console.print(f"[bold cyan][Agent] {mode} mode[/bold cyan]")
        jobs = self.repository.get_jobs_by_status(status=status)
        if not jobs:
            self.console.print("[yellow][Agent] No jobs found.[/yellow]")
            return

        self.console.print(f"[cyan][Agent] Applying to {len(jobs)} job(s)...[/cyan]")
        total_applied = self.application_service.run(page, jobs, mode=mode)
        self.console.print(
            f"[green][Agent] Applied to {total_applied} of {len(jobs)} job(s) found on {site}.[/green]"
        )

    def _run_site(self, pw, site: str, mode: JobAgentMode) -> None:
        self.console.print(f"[bold green][Agent] Starting run for site: {site}[/bold green]")
        session_manager, browser, context = self._create_session(pw, site)
        try:
            session_manager.ensure_logged_in(context)
            page: Page = context.new_page()

            if mode == JobAgentMode.QUICK_APPLY:
                self.default_apply_mode(page, site)
            else:
                mode_status_map = {
                    JobAgentMode.MANUAL_REVIEW: JobStatus.REQUIRES_MANUAL_REVIEW,
                    JobAgentMode.RERUN: JobStatus.FOUND,
                }
                self.status_based_run(page, site, mode, mode_status_map[mode])
        finally:
            context.close()
            browser.close()

    def run(self, mode: JobAgentMode) -> None:
        """Run the full job application pipeline."""
        with sync_playwright() as pw:
            sites = self.cfg.search.sites
            for site in sites:
                self._run_site(pw, site, mode)

            self.repository.to_csv()
            self.console.print("[bold green][Agent] Run complete — see Data/applications.csv[/bold green]")

    def debug(self, job: Job) -> None:
        with sync_playwright() as pw:
            session_manager, browser, context = self._create_session(pw, job.site)
            try:
                session_manager.ensure_logged_in(context)

                page: Page = context.new_page()
                page.goto(job.url, wait_until="load")

                site_classes = SiteRegistry.get(job.site)
                if site_classes is None:
                    self.console.print(f"[red][Debug] No applier registered for site '{job.site}'.[/red]")
                    return

                matcher = site_classes.matcher(self.repository, self.cfg)
                applier = site_classes.applier(self.repository, self.cfg, matcher)

                status = applier.apply(page, job)
                self.console.print(f"[green][Debug] Result: {status}[/green]")
                input("[Debug] Press Enter to close the browser and exit... ")
            finally:
                context.close()
                browser.close()
