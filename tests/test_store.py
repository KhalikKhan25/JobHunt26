from __future__ import annotations

import csv

from jobhunt.fetch import Job
from jobhunt.store import Store


def test_record_preserves_existing_tracker_fields_and_csv_columns(tmp_path):
    store = Store(tmp_path / "seen.json")
    job = Job("greenhouse:acme:1", "greenhouse", "Acme", "Engineer",
              "Bangalore", "https://example.com", "Go")
    store.data[job.job_id] = {
        "first_seen": "keep-first-seen",
        "company": "Keep company",
        "emailed": True,
        "applied": True,
        "applied_on": "keep-applied-date",
        "legacy_field": "keep-extra-data",
    }

    store.record([job], emailed=set())

    record = store.data[job.job_id]
    assert len(store.data) == 1
    assert record["first_seen"] == "keep-first-seen"
    assert record["company"] == "Keep company"
    assert record["emailed"] is True
    assert record["applied"] is True
    assert record["applied_on"] == "keep-applied-date"
    assert record["legacy_field"] == "keep-extra-data"

    csv_path = store.export_csv(tmp_path / "tracker.csv")
    with csv_path.open(encoding="utf-8", newline="") as file:
        assert next(csv.reader(file)) == [
            "job_id", "first_seen", "company", "title", "location",
            "score", "reason", "applied", "applied_on", "url",
        ]
