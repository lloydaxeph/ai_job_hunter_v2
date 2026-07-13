from __future__ import annotations

import argparse

from core.config import AppConfig
from core.constants import JobAgentMode
from core.job import Job
from db.database import Database
from db.job_repository import JobRepository
from orchestration.job_hunter_app import JobHunterApp
from reporting.report import JobReport


def _parse_mode(raw: str | None) -> JobAgentMode:
    """Match a --set mode=... value against JobAgentMode names or values,
    case- and separator-insensitive (accepts "quick_apply", "QUICK APPLY",
    "quick-apply", etc.). v1 compared the raw CLI string directly against
    the enum, which silently never matched for any mode but the default.
    """
    if raw is None:
        return JobAgentMode.QUICK_APPLY

    normalized = raw.strip().lower().replace("_", " ").replace("-", " ")
    for mode in JobAgentMode:
        if mode.value.lower() == normalized or mode.name.lower().replace("_", " ") == normalized:
            return mode

    valid = ", ".join(m.name.lower() for m in JobAgentMode)
    raise SystemExit(f"Unknown mode '{raw}'. Valid modes: {valid}")


def run_report() -> None:
    database = Database()
    repository = JobRepository(database.connection)
    JobReport(repository).print_summary()


def run_debug(cfg: AppConfig, options: dict[str, str]) -> None:
    debug_job = Job(
        title=options["debug.title"],
        company=options["debug.company"],
        url=options["debug.url"],
        site=options["debug.site"],
    )
    app = JobHunterApp(cfg, dry_run=False)
    app.debug(job=debug_job)


def run_pipeline(cfg: AppConfig, mode: JobAgentMode, dry_run: bool) -> None:
    keyword_num = len(cfg.search.keywords)
    location_num = len(cfg.search.locations)

    total_expected_jobs = cfg.search.max_results_per_site * (keyword_num * location_num)

    print("JobHunter Agent INITIATED!")
    print(f"MODE: {mode}{' (DRY RUN)' if dry_run else ''}")
    print(f"TOTAL EXPECTED JOBS: {total_expected_jobs}")

    app = JobHunterApp(cfg, dry_run=dry_run)
    app.run(mode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override runtime options (mode, debug.title, debug.company, debug.url, debug.site)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scraping and matching (including AI scoring) but stop before clicking Apply.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print application analytics from the existing database and exit.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )

    args = parser.parse_args()

    if args.report:
        run_report()
        return

    options: dict[str, str] = {}
    for item in args.set:
        key, value = item.split("=", 1)
        options[key] = value

    cfg = AppConfig.load(args.config)

    mode = _parse_mode(options.get("mode"))

    if mode == JobAgentMode.DEBUG:
        required = {"debug.title", "debug.company", "debug.url", "debug.site"}
        missing = required - options.keys()
        if missing:
            parser.error(
                f"DEBUG mode requires: {', '.join(sorted(required))} "
                f"(missing: {', '.join(sorted(missing))})"
            )
        run_debug(cfg, options)
    else:
        run_pipeline(cfg, mode, dry_run=args.dry_run)

    print("----------------------------------------------------")


if __name__ == "__main__":
    main()

    # sample commands
    # python main.py --set mode=quick_apply
    # python main.py --set mode=quick_apply --dry-run
    # python main.py --set mode=DEBUG --set debug.title="Software Engineer" \
    #     --set debug.company="Acme" --set debug.url="https://..." --set debug.site=linkedin
    # python main.py --report
