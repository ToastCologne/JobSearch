"""PowerPoint CV reader and writer using python-pptx."""
from pathlib import Path

from pptx import Presentation
from pptx.util import Pt


def extract_cv_text(cv_path: Path) -> str:
    """Extract all text from a PPTX file, preserving structure."""
    prs = Presentation(str(cv_path))
    sections: list[str] = []

    for slide_num, slide in enumerate(prs.slides, 1):
        slide_texts: list[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                text = "".join(run.text for run in para.runs).strip()
                if text:
                    slide_texts.append(text)
        if slide_texts:
            sections.append(f"--- Slide {slide_num} ---\n" + "\n".join(slide_texts))

    return "\n\n".join(sections)


def apply_amendments(
    cv_path: Path,
    amendments: dict,
    output_path: Path,
) -> None:
    """Apply AI-generated amendments to a copy of the PPTX."""
    import shutil

    shutil.copy2(str(cv_path), str(output_path))
    prs = Presentation(str(output_path))

    summary = amendments.get("professional_summary", "")
    text_replacements: list[tuple[str, str]] = []

    # Build replacement pairs from experience_amendments
    for amend in amendments.get("experience_amendments", []):
        original = amend.get("original_snippet", "").strip()
        amended = amend.get("amended_snippet", "").strip()
        if original and amended and original != amended:
            text_replacements.append((original, amended))

    if not text_replacements and not summary:
        return  # Nothing to change

    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            tf = shape.text_frame

            # Apply text replacements paragraph by paragraph
            for para in tf.paragraphs:
                para_text = "".join(run.text for run in para.runs)

                for original, amended in text_replacements:
                    if original in para_text:
                        # Replace text in runs while preserving formatting
                        _replace_text_in_para(para, original, amended)

                # Replace professional summary if the paragraph looks like one
                # (heuristic: paragraph > 30 chars on slide 1 near the top)
                if summary and _looks_like_summary(para_text):
                    _replace_text_in_para(para, para_text, summary)

    prs.save(str(output_path))


def _replace_text_in_para(para, original: str, replacement: str) -> None:
    """Replace text within a paragraph's runs, preserving formatting of first run."""
    if not para.runs:
        return

    # Combine all run text
    full_text = "".join(run.text for run in para.runs)
    if original not in full_text:
        return

    new_text = full_text.replace(original, replacement, 1)

    # Put all text in the first run, clear the rest
    para.runs[0].text = new_text
    for run in para.runs[1:]:
        run.text = ""


def _looks_like_summary(text: str) -> bool:
    """Heuristic: a summary paragraph is 50–500 chars and contains sentence-like content."""
    if len(text) < 50 or len(text) > 500:
        return False
    if text.count(" ") < 8:
        return False
    return True


def get_cv_text_for_ai(cv_path: Path) -> str:
    """Extract CV text, returning empty string if file doesn't exist."""
    if not cv_path.exists():
        return (
            "No CV file found at the configured path. "
            "Please add your CV (PowerPoint format) to the cv/ directory "
            "and update config.yaml with the correct path."
        )
    return extract_cv_text(cv_path)
