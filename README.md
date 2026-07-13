# AI Job Hunter Agent (v2)

An AI agent that searches, matches, and automatically applies to jobs using LLMs and browser automation.

This is a clean, object-oriented rewrite of the original prototype (`v1/`). Same core pipeline and feature set, restructured for extensibility (adding a new site touches a handful of files, not hundreds of duplicated lines) plus a few reliability and analytics improvements.

---

## Pipeline

```
Scraper -> Filter/Dedup -> Matcher -> Applier
```

1. **Scraper** — paginates a site's search results for each keyword x location pair, parses listings, and hands them to the filter/dedup step.
2. **Filter/Dedup** — drops banned companies/titles (`filtering/job_filter.py`) and skips jobs already saved to the database (`job_id` uniqueness).
3. **Matcher** (`matching/`) — for each surviving job: checks if you already applied, verifies it's a Quick Apply / Easy Apply listing, scrapes the full description, scores it against your profile via the LLM, and gates on `score_threshold`. Scoring and threshold logic live once in `matching/base.py`; only the three DOM checks are site-specific.
4. **Applier** (`appliers/`) — only runs if the Matcher passed: picks a resume (either the LLM's recommendation from scoring, or a keyword-match fallback), clicks apply, uploads the resume, fills unanswered form questions via the shared `FormFiller`, and submits.

Adding a new job site means writing three small classes — a `Scraper`, a `Matcher` (3 DOM hooks), and an `Applier` (upload/submit hooks) — then registering them in `orchestration/site_registry.py`. No form-filling or scoring logic needs to be duplicated.

---

## What changed from v1

- **OOP throughout** — `Config.py`'s free functions became `core/config.py: AppConfig` (a validated pydantic model); `JobStatus` became a real `Enum`.
- **Matcher split out of Applier** — v1 fused "is this a good job?" and "fill out this form" into one class per site. v2 separates them so scoring logic isn't duplicated.
- **Shared `FormFiller`** — v1's two ~230-line `fill_form` methods (LinkedIn/JobStreet) were ~90% identical. v2 has one `appliers/form_filler.py` parameterized by small per-site differences.
- **`SiteRegistry`** — replaces three duplicated if/elif site-dispatch blocks with one lookup table.
- **Retry + jitter** (`reliability/retry.py`) — flaky Playwright timeouts get a bounded retry instead of immediately failing the job; delay between applications is randomized instead of fixed.
- **AI-recommended resume** — the same scoring call that evaluates job fit now also recommends which resume to use, since it already sees the full job description (no extra API call).
- **Duplicate-score caching** — reposted listings at the same company/title reuse a prior score instead of paying for another LLM call.
- **`--dry-run`** — runs scraping + matching without ever clicking Apply. Useful after LinkedIn/JobStreet change their page layout.
- **`--report`** — prints funnel and per-site analytics from the existing database.

---

## Requirements

- Python 3.10+
- A valid OpenAI API key

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Add your resumes** to `Resumes/`, then reference them in `config.yaml`.

3. **Copy the config template** and fill it in:

   ```bash
   cp config.yaml.example config.yaml
   ```

4. **Copy the env template** and fill in your credentials:

   ```bash
   cp .env.example .env
   ```

   Never commit `.env` — it holds your OpenAI key and site login email/password.

## Running

```bash
# Normal run (job count controlled by search.max_results_per_site in config.yaml)
python main.py --set mode=quick_apply

# Dry run — scrape + score, never click Apply
python main.py --set mode=quick_apply --dry-run

# Re-run jobs that previously needed manual review
python main.py --set mode=manual_review

# Re-scrape-scored jobs that were only "found", not yet applied
python main.py --set mode=rerun

# Debug a single job URL end-to-end
python main.py --set mode=debug \
  --set debug.title="Software Engineer" \
  --set debug.company="Acme" \
  --set debug.url="https://..." \
  --set debug.site=linkedin

# Analytics over the existing database
python main.py --report
```

Modes are matched case- and separator-insensitively (`quick_apply`, `QUICK APPLY`, `quick-apply` all work).

---

## Database

SQLite (`Data/jobs.db`), no separate server required. Stores job postings, match scores, resume used, and application status. Exported to `Data/applications.csv` after every run.

---

## Disclaimer

Intended for educational and personal use. Review your configuration and ensure automated job applications comply with the terms of service of the platforms you target.
