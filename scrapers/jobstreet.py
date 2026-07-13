from core.job import Job
from db.job_repository import JobRepository
from filtering.job_filter import JobFilter
from scrapers.base import BaseScraper


class JobStreetScraper(BaseScraper):
    def __init__(self, repository: JobRepository, filter: JobFilter | None = None):
        super().__init__(
            site_name="jobstreet",
            base_url="https://sg.jobstreet.com",
            repository=repository,
            filter=filter,
        )

    def build_url(self, keyword: str, location: str) -> str:
        keyword = keyword.replace(" ", "-")
        location = location.replace(" ", "-")
        return f"{self.base_url}/{keyword}-jobs/in-{location}"

    def build_page_url(self, url: str, page_number: int) -> str:
        if page_number == 1:
            return url
        return f"{url}?page={page_number}"

    def has_next_page(self, page) -> bool:
        return (
            page.query_selector("a[aria-label='Next']") is not None
            or page.query_selector("a[data-testid='pagination-page-next']") is not None
        )

    def get_job_items(self, page):
        items = page.query_selector_all("[data-testid='job-card']")
        if not items:
            items = page.query_selector_all("article[class*='job']")
        return items

    def parse_job(self, item) -> Job | None:
        title = item.query_selector("[data-testid='job-title'], h1, h2, h3")
        if not title:
            return None

        company = item.query_selector(
            "[data-automation='jobCompany'], a[data-type='company']"
        )

        link = item.query_selector("a[href*='/job/']")
        href = ""
        if link:
            href = link.get_attribute("href") or ""
            if href.startswith("/"):
                href = self.base_url + href

        return Job(
            title=title.inner_text().strip(),
            company=company.inner_text().strip() if company else "",
            url=href,
            site=self.site_name,
        )
