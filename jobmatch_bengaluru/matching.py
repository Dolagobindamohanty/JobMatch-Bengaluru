"""Explainable Phase 4 resume-to-job matching."""
import re


def _tokens(text):
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", (text or "").lower()))


LEVELS = {"intern": 0, "entry": 1, "mid": 2, "senior": 3}


def score_match(profile, resume_text, job):
    resume_skills = set(profile.get("skills", []))
    job_skills = set(job.get("skills", []))
    matched = sorted(resume_skills & job_skills)
    missing = sorted(job_skills - resume_skills)
    skill_score = 100.0 if not job_skills else 100.0 * len(matched) / len(job_skills)

    resume_tokens = _tokens(resume_text)
    job_tokens = _tokens(f"{job.get('title', '')} {job.get('description', '')}")
    semantic_score = 100.0 * len(resume_tokens & job_tokens) / max(len(job_tokens), 1)

    resume_years = int(profile.get("years_of_experience", 0) or 0)
    expected = LEVELS.get(job.get("experience_level", "mid"), 2)
    actual = 0 if resume_years == 0 else 1 if resume_years < 2 else 2 if resume_years < 5 else 3
    experience_score = 100.0 if actual >= expected else max(40.0, 100.0 - (expected - actual) * 25)

    categories = profile.get("role_categories", [])
    title_fit = 100.0 if not categories or job.get("role_category") in categories else 50.0
    score = round(skill_score * .50 + semantic_score * .25 + experience_score * .15 + title_fit * .10, 2)
    return {
        "score": score, "skill_score": round(skill_score, 2),
        "semantic_score": round(semantic_score, 2),
        "experience_score": round(experience_score, 2),
        "title_score": round(title_fit, 2),
        "matched_skills": matched, "missing_skills": missing,
        "reason": f"Matched {len(matched)} of {len(job_skills)} listed skills; "
                  f"semantic overlap {semantic_score:.0f}% and experience fit {experience_score:.0f}%.",
    }
