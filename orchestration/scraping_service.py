from __future__ import annotations

from playwright.sync_api import Page

from core.config import SearchConfig
from core.job import Job
from core.logging import AppLogger
from db.job_repository import JobRepository
from filtering.job_filter import JobFilter
from orchestration.site_registry import SiteRegistry


class JobScrapingService:
    """Scrapes jobs for a site across every configured keyword x location pair."""

    def __init__(self, search_cfg: SearchConfig, job_filter: JobFilter, repository: JobRepository):
        self.cfg = search_cfg
        self.filter = job_filter
        self.repository = repository
        self.console = AppLogger.console()
        self.logger = AppLogger.logger()

    def scrape(self, page: Page, site: str) -> list[Job]:
        site_classes = SiteRegistry.get(site)
        if site_classes is None:
            self.logger.warning("No scraper registered for '%s'. Skipping.", site)
            return []

        scraper = site_classes.scraper(self.repository, self.filter)

        site_jobs: list[Job] = []
        for keyword in self.cfg.keywords:
            for location in self.cfg.locations:
                self.console.print(f"[cyan][Scraper] Searching {site}: '{keyword}' in '{location}'...[/cyan]")
                site_jobs.extend(
                    scraper.scrape(page, keyword, location, self.cfg.max_results_per_site)
                )

        self.console.print(f"[green][Scraper] Found {len(site_jobs)} new job(s) on {site}.[/green]")
        return site_jobs
