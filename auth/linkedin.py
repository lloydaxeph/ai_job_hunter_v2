from auth.base import BaseSessionManager


class LinkedInSessionManager(BaseSessionManager):
    def __init__(self):
        super().__init__(
            site_label="LinkedIn",
            session_dir="Sessions",
            session_file="linkedin.json",
            home_url="https://www.linkedin.com/feed/",
        )
