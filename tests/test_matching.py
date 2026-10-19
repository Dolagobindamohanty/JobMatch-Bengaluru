from jobmatch_bengaluru.matching import score_match


def test_match_score_is_explainable_and_rewards_skill_overlap():
    result = score_match(
        {"skills": ["python", "pytorch"], "years_of_experience": 3, "role_categories": ["ai_ml"]},
        "Python PyTorch machine learning engineer",
        {"title": "Machine Learning Engineer", "description": "Build Python models", "skills": ["python", "pytorch", "docker"], "experience_level": "mid", "role_category": "ai_ml"},
    )
    assert result["score"] > 60
    assert result["matched_skills"] == ["python", "pytorch"]
    assert result["missing_skills"] == ["docker"]
    assert "Matched" in result["reason"]
