"""AI-powered job matching."""
import json

from src.ai.provider import generate

SYSTEM = """You are an expert career coach and recruiter. Your task is to evaluate
how well a job posting matches a candidate's CV and specified preferences.

You must respond with ONLY valid JSON — no markdown, no extra text."""

PROMPT_TEMPLATE = """Evaluate this job posting against the candidate's CV.

=== CANDIDATE CV ===
{cv_text}

=== JOB CRITERIA ===
{criteria}

=== JOB POSTING ===
Title: {title}
Company: {company}
Location: {location}
Salary: {salary}
Description:
{description}

Respond with JSON in exactly this format:
{{
  "score": <integer 0-100>,
  "reasons": [
    "<key reason 1>",
    "<key reason 2>",
    "<key reason 3>"
  ],
  "summary": "<one sentence summary of the match>"
}}

Score guide:
- 80-100: Excellent match — strong skill alignment, good seniority fit
- 60-79:  Good match — most skills align, minor gaps
- 40-59:  Partial match — relevant field but missing key skills
- 20-39:  Weak match — some transferable skills
- 0-19:   Poor match — different field or very different seniority"""


def _build_criteria_text(cfg: dict) -> str:
    lines = []
    search = cfg.get("search", {})
    if search.get("queries"):
        lines.append(f"Desired roles: {', '.join(search['queries'])}")
    if search.get("location"):
        lines.append(f"Preferred location: {search['location']}")
    if search.get("remote"):
        lines.append("Remote work: preferred")
    s_min = search.get("salary_min")
    s_max = search.get("salary_max")
    if s_min or s_max:
        lines.append(f"Salary: {s_min or 'any'} – {s_max or 'any'}")
    req = cfg.get("matching", {}).get("required_keywords", [])
    if req:
        lines.append(f"Required keywords: {', '.join(req)}")
    return "\n".join(lines) if lines else "No specific criteria specified."


async def match_job(
    job: dict,
    cv_text: str,
    config: dict,
) -> tuple[int, list[str]]:
    """Return (score, reasons) for a job posting."""
    criteria = _build_criteria_text(config)
    prompt = PROMPT_TEMPLATE.format(
        cv_text=cv_text[:4000],
        criteria=criteria,
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        salary=job.get("salary", "Not specified"),
        description=job.get("description", "No description available")[:3000],
    )

    text = await generate(prompt, system=SYSTEM, max_tokens=512)

    try:
        data = json.loads(text)
        score = max(0, min(100, int(data.get("score", 0))))
        reasons = data.get("reasons", [])
        if isinstance(reasons, list):
            reasons = [str(r) for r in reasons[:5]]
        else:
            reasons = [str(reasons)]
        return score, reasons
    except (json.JSONDecodeError, ValueError):
        return 0, ["Could not parse AI response"]
