from core.job import Job
from db.job_repository import JobRepository
from filtering.job_filter import JobFilter
from scrapers.base import BaseScraper


class LinkedInScraper(BaseScraper):
    def __init__(self, repository: JobRepository, filter: JobFilter | None = None):
        super().__init__(
            site_name="linkedin",
            base_url="https://www.linkedin.com",
            repository=repository,
            filter=filter,
        )

    def build_url(self, keyword: str, location: str) -> str:
        keyword = keyword.replace(" ", "%20")
        location = location.replace(" ", "%20")
        return f"{self.base_url}/jobs/search/?keywords={keyword}&location={location}"

    def build_page_url(self, url: str, page_number: int) -> str:
        if page_number == 1:
            return url
        start = (page_number - 1) * 25
        return f"{url}&start={start}"

    def has_next_page(self, page) -> bool:
        selectors = [
            "button[aria-label='View next page']",
            "button.jobs-search-pagination__button--next",
        ]
        for selector in selectors:
            btn = page.query_selector(selector)
            if btn and btn.get_attribute("disabled") is None:
                return True
        return False

    def get_job_items(self, page):
        selectors = [
            "div[data-job-id]",
            "div.job-card-container",
            "li[data-occludable-job-id]",
            ".job-card-list",
        ]
        for selector in selectors:
            try:
                page.wait_for_selector(selector, timeout=10000)
                items = page.query_selector_all(selector)
                if items:
                    return items
            except TimeoutError:
                continue
        return []

    def parse_job(self, item) -> Job | None:
        title_el = item.query_selector("a[href*='/jobs/view/']")
        if not title_el:
            return None

        company_el = item.query_selector("[class*='entity-lockup__subtitle']")

        href = title_el.get_attribute("href") or ""
        if href.startswith("/"):
            href = self.base_url + href
        href = href.split("?")[0]

        title = title_el.inner_text().strip()
        if "\n" in title:
            title = title.split("\n")[0]

        return Job(
            title=title,
            company=company_el.inner_text().strip() if company_el else "",
            url=href,
            site=self.site_name,
        )
