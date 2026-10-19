"""Private resume parsing helpers used by Phase 3."""
import io
import re

from .classifiers import extract_skills

MAX_BYTES = 5 * 1024 * 1024


def extract_text(filename, content):
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if len(content) > MAX_BYTES:
        raise ValueError("Resume exceeds the 5 MB limit")
    if suffix == "txt":
        return content.decode("utf-8", errors="replace")
    if suffix == "pdf":
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("Install PDF support with: pip install PyMuPDF") from exc
        document = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in document)
    if suffix == "docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("Install DOCX support with: pip install python-docx") from exc
        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs)
    raise ValueError("Only PDF, DOCX, and TXT resumes are supported")


def parse_profile(text):
    text = text or ""
    years = [int(value) for value in re.findall(r"(\d{1,2})\+?\s+years?", text, re.I)]
    titles = sorted(set(re.findall(r"\b(?:software|data|machine learning|ml|backend|frontend|full[- ]stack|devops|cloud|qa|product)\s+(?:engineer|scientist|developer|analyst|manager)\b", text, re.I)))
    return {"skills": extract_skills(text), "job_titles": titles,
            "years_of_experience": max(years, default=0), "education": [],
            "projects": [], "tools": [], "technologies": []}
