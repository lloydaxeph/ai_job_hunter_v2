from __future__ import annotations

from abc import ABC, abstractmethod

from playwright.sync_api import Page

from core.job import Job
from core.logging import AppLogger
from db.job_repository import JobRepository
from filtering.job_filter import JobFilter


class BaseScraper(ABC):
    """Template method: paginate a search, parse each listing, filter + dedup + persist."""

    def __init__(self, site_name: str, base_url: str, repository: JobRepository, filter: JobFilter | None = None):
        self.site_name = site_name
        self.base_url = base_url
        self.repository = repository
        self.filter = filter
        self.console = AppLogger.console()

    def uses_in_place_pagination(self) -> bool:
        """Override to True for sites that append results in place (e.g. a 'Show more'
        button) instead of navigating to a new page URL."""
        return False

    def scrape(self, page: Page, keyword: str, location: str, max_results: int) -> list[Job]:
        jobs: list[Job] = []
        page_number = 1

        try:
            base_url = self.build_url(keyword, location)

            while len(jobs) < max_results:
                if page_number == 1 or not self.uses_in_place_pagination():
                    page_url = self.build_page_url(base_url, page_number)
                    page.goto(page_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                items = self.get_job_items(page)
                if not items:
                    break

                for item in items:
                    if len(jobs) >= max_results:
                        break
                    try:
                        job = self.parse_job(item)
                        if not job:
                            continue

                        if self.filter and self.filter.should_skip(job):
                            continue

                        if self.repository.save(job):
                            jobs.append(job)

                    except Exception:
                        continue

                self.console.print(f"[cyan][Scraper] {len(jobs)} new job(s) collected so far...[/cyan]")

                if len(jobs) >= max_results:
                    break

                if not self.has_next_page(page):
                    break

                page_number += 1

            return jobs

        except Exception as e:
            self.console.print(f"[red][Scraper] Scraping failed: {e}[/red]")
            return []

    @abstractmethod
    def build_url(self, keyword: str, location: str) -> str:
        """Build the search URL."""

    @abstractmethod
    def build_page_url(self, url: str, page_number: int) -> str:
        """Build the URL for a specific page."""

    @abstractmethod
    def has_next_page(self, page: Page) -> bool:
        """Return True if another results page exists."""

    @abstractmethod
    def get_job_items(self, page: Page):
        """Return the raw listing elements on the current page."""

    @abstractmethod
    def parse_job(self, item) -> Job | None:
        """Parse a raw listing element into a Job."""
