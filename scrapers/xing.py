from core.job import Job
from db.job_repository import JobRepository
from filtering.job_filter import JobFilter
from scrapers.base import BaseScraper


class XingScraper(BaseScraper):
    def __init__(self, repository: JobRepository, filter: JobFilter | None = None):
        super().__init__(
            site_name="xing",
            base_url="https://www.xing.com",
            repository=repository,
            filter=filter,
        )

    def uses_in_place_pagination(self) -> bool:
        return True

    def build_url(self, keyword: str, location: str) -> str:
        keyword = keyword.replace(" ", "%20")
        location = location.replace(" ", "%20")
        return f"{self.base_url}/jobs/search?keywords={keyword}&location={location}"

    def build_page_url(self, url: str, page_number: int) -> str:
        return url

    def has_next_page(self, page) -> bool:
        button = page.query_selector("button[data-testid='show-more-button']")
        if not button:
            buttons = page.query_selector_all("button")
            button = next(
                (b for b in buttons if (b.inner_text() or "").strip().lower() == "show more"),
                None,
            )

        if not button or button.get_attribute("aria-disabled") == "true":
            return False

        try:
            count_before = len(self.get_job_items(page))
            button.scroll_into_view_if_needed()
            button.click()
            page.wait_for_function(
                "count => document.querySelectorAll(\"article[data-testid='job-search-result']\").length > count",
                arg=count_before,
                timeout=10000,
            )
            return True
        except Exception:
            return False

    def get_job_items(self, page):
        return page.query_selector_all("article[data-testid='job-search-result']")

    def parse_job(self, item) -> Job | None:
        title_el = item.query_selector("h2[data-testid='job-teaser-list-title']")
        if not title_el:
            return None

        company_el = item.query_selector("p[class*='job-teaser-list-item-styles__Company']")

        link = item.query_selector("a[class*='CardLink']")
        href = ""
        if link:
            href = link.get_attribute("href") or ""
            if href.startswith("/"):
                href = self.base_url + href
            href = href.split("?")[0]

        return Job(
            title=title_el.inner_text().strip(),
            company=company_el.inner_text().strip() if company_el else "",
            url=href,
            site=self.site_name,
        )
