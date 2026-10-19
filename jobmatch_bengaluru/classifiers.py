"""Deterministic, explainable Phase 1 job classifiers."""
import re

ROLE_PATTERNS = {
    "ai_ml": r"\b(ai|artificial intelligence|machine learning|ml engineer|deep learning|genai|llm|nlp|computer vision|mlops|robotics)\b",
    "data_science": r"\b(data scientist|data science|analytics scientist|quantitative analyst)\b",
    "data_engineering": r"\b(data engineer|analytics engineer|etl|data platform)\b",
    "software_engineering": r"\b(software|backend|frontend|full[- ]stack|mobile|web)\b.*\b(engineer|developer)|\b(engineer|developer)\b",
    "devops_sre": r"\b(devops|site reliability|\bsre\b|platform engineer|infrastructure)\b",
    "security": r"\b(cyber|security|application security|information security)\b",
    "qa_testing": r"\b(qa|quality assurance|test engineer|automation test)\b",
    "technical_support": r"\b(technical account|technical support|solutions engineer|support engineer)\b",
}

SKILLS = {
    "python": ["python"], "java": ["java"], "javascript": ["javascript", "js"],
    "typescript": ["typescript", "ts"], "sql": ["sql"], "c++": ["c++"],
    "go": ["golang", "go"], "aws": ["aws", "amazon web services"],
    "azure": ["azure"], "gcp": ["gcp", "google cloud"],
    "docker": ["docker"], "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"], "git": ["git"], "linux": ["linux"],
    "postgresql": ["postgresql", "postgres"], "mongodb": ["mongodb", "mongo"],
    "pytorch": ["pytorch"], "tensorflow": ["tensorflow"],
    "scikit-learn": ["scikit-learn", "sklearn"], "pandas": ["pandas"],
    "numpy": ["numpy"], "spark": ["apache spark", "spark"],
    "airflow": ["airflow"], "mlflow": ["mlflow"], "llm": ["llm", "large language model"],
    "nlp": ["nlp", "natural language processing"], "computer vision": ["computer vision"],
    "generative ai": ["generative ai", "genai"], "machine learning": ["machine learning"],
}


def classify_role_category(title, description=""):
    text = f"{title} {description}".lower()
    for category, pattern in ROLE_PATTERNS.items():
        if re.search(pattern, text, re.I):
            return category
    return "other"


def classify_experience(title, description=""):
    text = f"{title} {description}".lower()
    if re.search(r"\bintern(ship)?\b|\bco[- ]?op\b|early career", text):
        return "intern"
    if re.search(r"\b(entry[- ]level|junior|associate|graduate|fresher)\b", text):
        return "entry"
    if re.search(r"\b(principal|staff|lead|director|head|vp|vice president)\b", text):
        return "senior"
    if re.search(r"\b(senior|sr\.?|manager|architect)\b", text):
        return "senior"
    return "mid"


def extract_skills(text):
    text = text or ""
    found = []
    for canonical, aliases in SKILLS.items():
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.I) for alias in aliases):
            found.append(canonical)
    return sorted(found)
