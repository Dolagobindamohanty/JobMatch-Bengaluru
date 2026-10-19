"""Local fixtures for the Bengaluru jobs pipeline tests."""

import os

import pytest


# Existing API tests exercise the optional resume/account flows. Keep their
# local behavior explicit while production defaults to the safe disabled state.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JOBMATCH_RESUME_ENABLED", "true")


@pytest.fixture
def greenhouse_payload():
    return {
        "jobs": [
            {
                "id": 101,
                "title": "Machine Learning Engineer",
                "location": {"name": "Bengaluru, Karnataka"},
                "absolute_url": "https://jobs.example/101",
                "updated_at": "2026-01-02T03:04:05Z",
                "content": "<p>Build <strong>ML</strong> models &amp; services.</p>",
            },
            {
                "id": 102,
                "title": "Product Marketing Manager",
                "location": {"name": "Bangalore"},
                "absolute_url": "https://jobs.example/102",
                "updated_at": "2026-01-02T03:04:05Z",
                "content": "Lead campaigns for our products.",
            },
            {
                "id": 103,
                "title": "Backend Engineer",
                "location": {"name": "Remote - India"},
                "absolute_url": "https://jobs.example/103",
                "updated_at": "2026-01-02T03:04:05Z",
                "content": "Build APIs.",
            },
        ]
    }


@pytest.fixture
def lever_payload():
    return [
        {
            "id": "lever-1",
            "text": "Data Engineer",
            "categories": {"location": "India", "allLocations": ["Bengaluru"]},
            "descriptionPlain": "Own data pipelines.",
            "createdAt": 1767323045000,
            "hostedUrl": "https://jobs.example/lever-1",
        },
        {
            "id": "lever-2",
            "text": "Recruiter",
            "categories": {"location": "Bengaluru", "allLocations": []},
            "descriptionPlain": "Hire great people.",
            "createdAt": 1767323045000,
            "hostedUrl": "https://jobs.example/lever-2",
        },
    ]


@pytest.fixture
def ashby_payload():
    return {
        "jobs": [
            {
                "id": "ashby-1",
                "title": "AI Platform Engineer",
                "location": "Remote",
                "secondaryLocations": [{"location": "BLR"}],
                "descriptionPlain": "Operate model serving infrastructure.",
                "jobUrl": "https://jobs.example/ashby-1",
                "publishedAt": "2026-01-03T00:00:00Z",
            }
        ]
    }


@pytest.fixture
def workday_jobs():
    return [
        {
            "bulletFields": ["wd-1"],
            "title": "SRE - Bangalore",
            "locationsText": "Bangalore",
            "externalPath": "/en-US/job/wd-1",
            "postedOn": "2026-01-04",
        },
        {
            "bulletFields": ["wd-2"],
            "title": "Finance Analyst",
            "locationsText": "Bengaluru",
            "externalPath": "/en-US/job/wd-2",
            "postedOn": "2026-01-04",
        },
    ]
