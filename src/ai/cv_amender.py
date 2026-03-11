"""AI-powered CV amendment using Claude (streaming)."""
import json

import anthropic

from src.config import get_anthropic_key

MODEL = "claude-opus-4-6"

SYSTEM = """You are an expert CV writer and career consultant. Your task is to
tailor a candidate's CV for a specific job posting, highlighting the most
relevant experience and skills WITHOUT fabricating anything.

You must respond with ONLY valid JSON — no markdown, no extra text."""

PROMPT_TEMPLATE = """Tailor this CV for the job posting below.
Keep all facts accurate — only reorder, rephrase, and emphasise relevant points.

=== ORIGINAL CV TEXT ===
{cv_text}

=== TARGET JOB ===
Title: {title}
Company: {company}
Description:
{description}

Return JSON with this exact structure:
{{
  "professional_summary": "<2-3 sentence tailored summary>",
  "key_skills": ["skill1", "skill2", "skill3", "...up to 10 skills"],
  "experience_amendments": [
    {{
      "original_snippet": "<exact text from CV to replace>",
      "amended_snippet": "<replacement text, same length, more relevant>"
    }}
  ],
  "cover_letter_hooks": [
    "<key selling point 1 to mention in cover letter>",
    "<key selling point 2>",
    "<key selling point 3>"
  ]
}}

Rules:
- Keep experience_amendments to 3–5 impactful changes
- Only amend bullet points you can make more relevant
- The original_snippet must be findable verbatim in the CV text above
- Do NOT add skills or experience the candidate doesn't have"""


async def amend_cv(job: dict, cv_text: str) -> dict:
    """Stream CV amendments from Claude. Returns amendment dict."""
    client = anthropic.AsyncAnthropic(api_key=get_anthropic_key())

    prompt = PROMPT_TEMPLATE.format(
        cv_text=cv_text[:5000],
        title=job.get("title", ""),
        company=job.get("company", ""),
        description=job.get("description", "")[:3000],
    )

    text_chunks: list[str] = []
    async with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for chunk in stream.text_stream:
            text_chunks.append(chunk)

    full_text = "".join(text_chunks)

    try:
        return json.loads(full_text)
    except json.JSONDecodeError:
        # Try to extract JSON from the text
        import re
        match = re.search(r"\{.*\}", full_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {
            "professional_summary": "",
            "key_skills": [],
            "experience_amendments": [],
            "cover_letter_hooks": [],
            "error": "Could not parse AI response",
        }
