from auth.base import BaseSessionManager


class XingSessionManager(BaseSessionManager):
    def __init__(self):
        super().__init__(
            site_label="Xing",
            session_dir="Sessions",
            session_file="xing.json",
            home_url="https://www.xing.com/jobs/search",
        )
