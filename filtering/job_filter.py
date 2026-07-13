from core.job import Job
from core.logging import AppLogger


class JobFilter:
    """Decides which scraped jobs are worth keeping."""

    def __init__(self, banned_companies: list[str], avoid_titles: list[str] | None = None):
        self.banned_companies = [c.lower() for c in banned_companies]
        self.avoid_titles = [t.lower() for t in (avoid_titles or [])]
        self.console = AppLogger.console()
        self.app = "[Filter]"

    def is_banned_company(self, job: Job) -> bool:
        company = job.company.lower()
        for banned in self.banned_companies:
            if banned in company:
                self.console.print(
                    f"[yellow]{self.app} Skipping '{job.title}' — banned company '{job.company}'.[/yellow]"
                )
                return True
        return False

    def is_avoided_title(self, job: Job) -> bool:
        title = job.title.lower()
        for keyword in self.avoid_titles:
            if keyword in title:
                self.console.print(
                    f"[yellow]{self.app} Skipping '{job.title}' @ '{job.company}' — avoided title keyword '{keyword}'.[/yellow]"
                )
                return True
        return False

    def should_skip(self, job: Job) -> bool:
        return self.is_banned_company(job) or self.is_avoided_title(job)
