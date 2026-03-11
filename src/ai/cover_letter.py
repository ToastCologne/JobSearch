"""AI-powered cover letter generation."""
from src.ai.provider import generate

SYSTEM = """You are an expert cover letter writer. Write compelling, specific,
and authentic cover letters that highlight genuine fit without being sycophantic.
Write in first person. Be concise (3–4 paragraphs). Do not use filler phrases
like 'I am excited to apply' or 'I believe I would be a great fit'."""

PROMPT_TEMPLATE = """Write a cover letter for this job application.

=== CANDIDATE CV ===
{cv_text}

=== JOB ===
Title: {title}
Company: {company}
Description:
{description}

=== KEY SELLING POINTS TO HIGHLIGHT ===
{hooks}

Requirements:
- 3–4 paragraphs
- Opening: specific reason for interest in this company/role
- Middle 1-2 paragraphs: concrete examples from CV that match job requirements
- Closing: clear call to action
- Tone: professional but personable
- Length: 250-350 words
- Do NOT use placeholder text like [Your Name] — write as if ready to send
- Start with 'Dear Hiring Manager,'"""


async def generate_cover_letter(
    job: dict,
    cv_text: str,
    hooks: list[str] | None = None,
) -> str:
    """Generate a cover letter. Returns the full letter text."""
    hooks_text = "\n".join(f"- {h}" for h in (hooks or [])) or "Focus on most relevant experience."

    prompt = PROMPT_TEMPLATE.format(
        cv_text=cv_text[:4000],
        title=job.get("title", ""),
        company=job.get("company", ""),
        description=job.get("description", "")[:3000],
        hooks=hooks_text,
    )

    return await generate(prompt, system=SYSTEM, max_tokens=1024)
