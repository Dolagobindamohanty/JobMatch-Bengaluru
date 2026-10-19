# Phase 3 Status

## Implemented

- Resume parser package: `jobmatch_bengaluru/resume_parser.py`
- PDF parsing through PyMuPDF when installed
- DOCX parsing through python-docx when installed
- TXT parsing for local smoke tests
- 5 MB upload limit
- Private local storage under `resume_uploads/`
- Parsed profile extraction:
  - skills
  - job titles
  - years of experience
  - education/projects/tools/technologies placeholders for later refinements
- Resume upload endpoint: `POST /resumes`
- Resume profile endpoint: `GET /resumes/{id}`
- Editable skill endpoint: `PATCH /resumes/{id}/skills`
- Resume deletion endpoint: `DELETE /resumes/{id}`
- File deletion when the resume is deleted
- Upload, edit, read-back, delete, and size-limit tests

## Verification

```text
python -m pytest tests -q
13 passed, 1 xpassed

python -m py_compile api/app/main.py jobmatch_bengaluru/resume_parser.py
passed
```

## Install parser support

From the project root:

```powershell
pip install -r api/requirements.txt
```

The current tests use TXT input so they can run without binary parser packages.
After installing the requirements, PDF and DOCX uploads are enabled.

## Important limitation

The current API uses a local-user identity (`local-user`) because authentication
belongs to Phase 6. It is suitable for local development only. Before public
deployment, replace it with authenticated user IDs and private object storage.
