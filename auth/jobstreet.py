from auth.base import BaseSessionManager


class JobStreetSessionManager(BaseSessionManager):
    def __init__(self):
        super().__init__(
            site_label="JobStreet",
            session_dir="Sessions",
            session_file="jobstreet.json",
            home_url="https://sg.jobstreet.com",
        )
