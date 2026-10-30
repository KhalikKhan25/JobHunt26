from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhunt import cli
from jobhunt.fetch import Job


class ScreenProvider:
    name = "stub-screen"

    def complete(self, model, system, user, max_tokens, json_mode=False):
        payload = json.loads(user.split("JOBS:\n", 1)[1])
        return json.dumps([
            {"job_id": item["job_id"],
             "score": 8 if item["job_id"].endswith(":1") else 4,
             "reason": "matches required experience"}
            for item in payload
        ])


class DraftProvider:
    name = "stub-draft"

    def __init__(self):
        self.calls = 0

    def complete(self, model, system, user, max_tokens, json_mode=False):
        self.calls += 1
        if self.calls == 1:
            from jobhunt.providers import LLMError
            raise LLMError("temporary Gemini HTTP 503")
        return json.dumps({
            "fit_summary": "Good fit",
            "tailored_bullets": [],
            "gaps": [],
            "cover_note": "Draft note",
            "questions_to_ask": [],
        })


def test_failed_draft_retries_without_duplicate_records_or_emails(
        tmp_path, monkeypatch, capsys):
    profile_file = tmp_path / "profile.json"
    profile_file.write_text("{}", encoding="utf-8")
    companies_file = tmp_path / "companies.yaml"
    companies_file.write_text(
        "companies:\n  - ats: greenhouse\n    slug: acme\n", encoding="utf-8")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump({
        "profile_file": str(profile_file),
        "companies_file": str(companies_file),
        "seen_file": str(tmp_path / "seen.json"),
        "digest_file": str(tmp_path / "digest.html"),
        "tracker_csv": str(tmp_path / "tracker.csv"),
        "filters": {},
        "score_threshold": 7,
        "max_per_digest": 5,
    }), encoding="utf-8")

    def jobs_for_run():
        return [
            Job("greenhouse:acme:1", "greenhouse", "Acme", "Backend Engineer",
                "Bangalore", "https://example.com/1", "Go and Kubernetes"),
            Job("greenhouse:acme:2", "greenhouse", "Acme", "Backend Engineer",
                "Bangalore", "https://example.com/2", "Different position"),
        ]

    draft_provider = DraftProvider()
    screen_provider = ScreenProvider()
    monkeypatch.setattr(cli, "fetch_all", lambda _: jobs_for_run())
    monkeypatch.setattr(
        cli, "resolve",
        lambda stage: (screen_provider, "screen") if stage == "screen"
        else (draft_provider, "draft"))
    sent = []
    monkeypatch.setattr(cli.mailer, "send", lambda subject, body: sent.append(body))

    args = SimpleNamespace(
        config=str(config_file), mock=False, scorer="llm", limit=None,
        no_draft=False, send=True,
    )

    assert cli.cmd_run(args) == 0
    assert sent == []

    assert cli.cmd_run(args) == 0
    assert len(sent) == 1
    assert "greenhouse:acme:1" in sent[0]
    assert "greenhouse:acme:2" not in sent[0]

    assert cli.cmd_run(args) == 0
    assert len(sent) == 1
    assert draft_provider.calls == 2

    from jobhunt.store import Store
    store = Store(tmp_path / "seen.json")
    assert store.stats() == {"tracked": 2, "emailed": 1, "applied": 0}
    assert store.data["greenhouse:acme:1"]["draft_status"] == "generated"
    assert store.data["greenhouse:acme:1"]["applied"] is False
    assert store.data["greenhouse:acme:2"]["emailed"] is False
    output = capsys.readouterr().out
    assert output.count("draft retries pending: 1") == 1
    assert "selected; match reason: matches required experience" in output
    assert "score below threshold 7.0" in output
