from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Browser, BrowserContext

from core.logging import AppLogger


class BaseSessionManager:
    """Persists a logged-in Playwright session to disk via storage_state.

    Login itself is manual (the user completes 2FA/CAPTCHA in the opened
    browser) — this class only decides whether a fresh login is needed and
    where the session gets cached.
    """

    def __init__(self, site_label: str, session_dir: str, session_file: str, home_url: str):
        self.site_label = site_label
        self.session_dir = Path(session_dir)
        self.session_file = self.session_dir / session_file
        self.home_url = home_url
        self.console = AppLogger.console()

    def create_context(self, browser: Browser) -> BrowserContext:
        self.session_dir.mkdir(exist_ok=True)

        if self.session_file.exists():
            self.console.print(f"[SESSION] Loading existing session: {self.session_file.name}")
            return browser.new_context(storage_state=str(self.session_file))

        self.console.print("[SESSION] Creating new browser session...")
        return browser.new_context()

    def clear_session(self) -> None:
        if self.session_file.exists():
            self.session_file.unlink()
            self.console.print(f"[SESSION] Removed session: {self.session_file.name}")

    def ensure_logged_in(self, context: BrowserContext) -> None:
        if self.session_file.exists():
            return

        page = context.new_page()
        page.goto(self.home_url)

        self.console.print("")
        self.console.print("=" * 60)
        self.console.print("MANUAL LOGIN REQUIRED")
        self.console.print("=" * 60)
        self.console.print(f"1. Log in to {self.site_label}.")
        self.console.print("2. Complete OTP/CAPTCHA/2FA if prompted.")
        self.console.print("3. Wait until the page is fully loaded.")
        self.console.print("=" * 60)

        input("[SESSION] Press ENTER after logging in...")

        context.storage_state(path=str(self.session_file))
        self.console.print(f"[SESSION] Session saved to {self.session_file}")

        page.close()
