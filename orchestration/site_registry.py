from __future__ import annotations

from dataclasses import dataclass

from appliers.base import BaseApplier
from appliers.jobstreet import JobStreetApplier
from appliers.linkedin import LinkedInApplier
from appliers.xing import XingApplier
from auth.base import BaseSessionManager
from auth.jobstreet import JobStreetSessionManager
from auth.linkedin import LinkedInSessionManager
from auth.xing import XingSessionManager
from matching.base import Matcher
from matching.jobstreet import JobStreetMatcher
from matching.linkedin import LinkedInMatcher
from matching.xing import XingMatcher
from scrapers.base import BaseScraper
from scrapers.jobstreet import JobStreetScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.xing import XingScraper


@dataclass(frozen=True)
class SiteClasses:
    scraper: type[BaseScraper]
    matcher: type[Matcher]
    applier: type[BaseApplier]
    session_manager: type[BaseSessionManager]


class SiteRegistry:
    """Single lookup point mapping a site name to its Scraper/Matcher/Applier/
    SessionManager classes. Replaces the if/elif dispatch that v1 duplicated
    in JobScraper.get_scraper, JobApplier.get_applier, and
    SessionManager.get_manager.

    Adding a new site means registering one entry here — no other call site
    needs to change.
    """

    _REGISTRY: dict[str, SiteClasses] = {
        "linkedin": SiteClasses(
            scraper=LinkedInScraper,
            matcher=LinkedInMatcher,
            applier=LinkedInApplier,
            session_manager=LinkedInSessionManager,
        ),
        "jobstreet": SiteClasses(
            scraper=JobStreetScraper,
            matcher=JobStreetMatcher,
            applier=JobStreetApplier,
            session_manager=JobStreetSessionManager,
        ),
        "xing": SiteClasses(
            scraper=XingScraper,
            matcher=XingMatcher,
            applier=XingApplier,
            session_manager=XingSessionManager,
        ),
    }

    @classmethod
    def get(cls, site: str) -> SiteClasses | None:
        return cls._REGISTRY.get(site.lower())

    @classmethod
    def register(cls, site: str, classes: SiteClasses) -> None:
        cls._REGISTRY[site.lower()] = classes
