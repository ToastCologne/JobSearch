# Job Search Bot

An AI-powered job application assistant that scrapes LinkedIn, Indeed, Glassdoor, and company career pages, matches jobs against your CV using Claude, and helps you apply with a tailored CV, cover letter, and pre-filled application form.

## Features

- **Multi-site scraping** — LinkedIn, Indeed, Glassdoor, and custom company career pages
- **AI job matching** — Claude scores each job (0–100) against your CV and criteria
- **CV amendment** — Claude tailors your PowerPoint CV for each application
- **Cover letter generation** — Claude writes a personalised cover letter
- **Form pre-filling** — Playwright fills in the application form for your review
- **Web dashboard** — Review matches, manage applications, download documents
- **Session persistence** — Log in once per site; cookies are saved across runs
- **Scheduler** — Optionally run scraping automatically on a cron schedule

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Edit config.yaml with your:
# - Job search queries and location
# - Which sites to scrape
# - Salary preferences
# - Minimum match score threshold
```

### 3. Add your CV

Place your CV (PowerPoint format) at `cv/template.pptx` (or update `cv.path` in `config.yaml`).

### 4. Run setup

```bash
python main.py setup
```

### 5. Log in to job sites (first time only)

```bash
python main.py login linkedin
python main.py login indeed
python main.py login glassdoor
```

Your session cookies are saved in `browser_profile/` and reused automatically.

### 6. Start the dashboard

```bash
python main.py dashboard
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### 7. Scrape jobs

Click **"Scrape Jobs Now"** in the dashboard, or run:

```bash
python main.py scrape
```

## Dashboard Workflow

1. **Review matches** — Jobs are scored 0–100. Click any job to see why it matched.
2. **Set status** — Mark jobs as *Interested*, *Reviewing*, *Rejected*, etc.
3. **Amend CV** — Click "Amend CV for this Job" — Claude tailors your CV in ~30 seconds.
4. **Generate cover letter** — Claude writes a personalised letter in ~20 seconds.
5. **Pre-fill form** — Click "Pre-fill Application Form" — Playwright opens the application page and fills in your details. **Review carefully before submitting.**
6. **Submit** — You click Submit in the browser. The bot never submits automatically.

## Scheduler

To enable automatic daily scraping, set in `config.yaml`:

```yaml
scheduler:
  enabled: true
  cron: "0 9 * * 1-5"  # weekdays at 9am
```

Then restart the dashboard.

## Configuration Reference

| Key | Description |
|-----|-------------|
| `cv.path` | Path to your CV (.pptx) |
| `search.queries` | Job title keywords to search |
| `search.location` | Location string |
| `search.remote` | Include remote jobs |
| `search.salary_min/max` | Salary range filter |
| `search.sites.*` | Enable/disable each site |
| `search.company_pages` | List of company career page URLs |
| `matching.min_score` | Minimum AI score to display (0–100) |
| `matching.required_keywords` | Hard-filter: must contain these words |
| `matching.excluded_keywords` | Hard-filter: exclude if contains these |
| `scheduler.enabled` | Auto-run on schedule |
| `scheduler.cron` | Cron expression (5 fields) |
| `dashboard.host/port` | Dashboard server address |

## Notes

- **Never clicks Submit** — The form filler pre-fills fields and takes a screenshot for review. You always manually click Submit.
- **Anti-bot measures** — LinkedIn and Glassdoor have anti-scraping protections. The bot uses realistic delays and browser fingerprinting mitigation, but may occasionally be blocked.
- **Company pages** — Generic scraping works for most pages but may need tuning for specific sites.
