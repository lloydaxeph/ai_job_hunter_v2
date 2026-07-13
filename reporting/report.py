from __future__ import annotations

from collections import Counter, defaultdict

from rich.console import Console
from rich.table import Table

from core.constants import JobStatus
from db.job_repository import JobRepository


class JobReport:
    """Read-only analytics over the jobs table: funnel counts, apply success
    rate by site, and average score by site. Purely additive — no schema
    change, reuses data already persisted by the normal pipeline run.
    """

    def __init__(self, repository: JobRepository):
        self.repository = repository
        self.console = Console()

    def print_summary(self) -> None:
        jobs = self.repository.get_all()

        if not jobs:
            self.console.print("[yellow]No jobs in the database yet.[/yellow]")
            return

        self._print_funnel(jobs)
        self._print_site_breakdown(jobs)

    def _print_funnel(self, jobs) -> None:
        status_counts = Counter(str(job.status) for job in jobs)

        table = Table(title="Funnel")
        table.add_column("Status")
        table.add_column("Count", justify="right")

        for status in JobStatus:
            table.add_row(status.value, str(status_counts.get(status.value, 0)))

        table.add_row("TOTAL", str(len(jobs)))
        self.console.print(table)

    def _print_site_breakdown(self, jobs) -> None:
        by_site: dict[str, list] = defaultdict(list)
        for job in jobs:
            by_site[job.site].append(job)

        table = Table(title="By Site")
        table.add_column("Site")
        table.add_column("Scraped", justify="right")
        table.add_column("Applied", justify="right")
        table.add_column("Success Rate", justify="right")
        table.add_column("Avg Score", justify="right")

        for site, site_jobs in sorted(by_site.items()):
            applied = sum(1 for job in site_jobs if str(job.status) == JobStatus.APPLIED.value)
            scored = [job.score for job in site_jobs if job.score > 0]
            avg_score = sum(scored) / len(scored) if scored else 0.0
            success_rate = applied / len(site_jobs) if site_jobs else 0.0

            table.add_row(
                site,
                str(len(site_jobs)),
                str(applied),
                f"{success_rate:.0%}",
                f"{avg_score:.1f}",
            )

        self.console.print(table)
