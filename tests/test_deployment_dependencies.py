"""The web service also launches the collector in its deployed environment."""
from pathlib import Path


def test_render_installs_collector_http_dependency():
    requirements = (Path(__file__).resolve().parents[1] / "api" / "requirements.txt").read_text()
    assert any(line.strip().startswith("requests>=") for line in requirements.splitlines())
