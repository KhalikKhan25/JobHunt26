"""Deterministic filter that runs BEFORE any LLM call.

This is the whole cost story: ~2000 raw jobs -> ~40 candidates for ~0 rupees,
so Claude only ever reads jobs that already passed title + location + freshness.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .fetch import Job

REMOTE_HINTS = ("remote", "anywhere", "work from home", "wfh", "distributed")
DIAGNOSTIC_SAMPLES = 3


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.fromisoformat(v) if fmt is None else datetime.strptime(v, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def prefilter(jobs: list[Job], cfg: dict) -> list[Job]:
    inc = cfg.get("include_titles") or [r"."]
    exc = cfg.get("exclude_titles") or []
    locs = [l.lower() for l in (cfg.get("locations") or [])]
    allow_remote = bool(cfg.get("allow_remote", True))
    max_age = cfg.get("max_age_days")
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age) if max_age else None

    kept, stats = [], {"title": 0, "location": 0, "age": 0}
    examples: dict[str, list[str]] = {
        "title": [], "location": [], "age": [], "matched": [],
    }

    def add_example(category: str, message: str) -> None:
        if len(examples[category]) < DIAGNOSTIC_SAMPLES:
            examples[category].append(message)

    for j in jobs:
        include_pattern = next((p for p in inc if re.search(p, j.title, re.I)), None)
        include_match = include_pattern is not None
        excluded_by = (next((p for p in exc if re.search(p, j.title, re.I)), None)
                       if include_match else None)
        if not include_match or excluded_by is not None:
            stats["title"] += 1
            reason = (f"excluded by title pattern {excluded_by!r}" if excluded_by
                      else "no include-title pattern matched")
            add_example("title", f"{j.job_id} ({j.title!r}): {reason}")
            continue

        is_remote = False
        location_match = None
        if locs:
            hay = f"{j.location} {j.title}".lower()
            is_remote = allow_remote and any(h in hay for h in REMOTE_HINTS)
            location_match = next((loc for loc in locs if loc in hay), None)
            location_matches = any(loc in hay for loc in locs)
            if not is_remote and not location_matches:
                stats["location"] += 1
                add_example("location", f"{j.job_id} ({j.title!r}): "
                            f"location {j.location!r} did not match configured locations")
                continue

        posted = _parse_date(j.posted_at) if cutoff else None
        if cutoff:
            if posted and posted < cutoff:
                stats["age"] += 1
                add_example("age", f"{j.job_id} ({j.title!r}): "
                            f"posted {j.posted_at} is older than {max_age} days")
                continue

        location_reason = ("remote posting allowed" if is_remote else
                           f"location matched {location_match!r}" if locs else
                           "location filter disabled")
        freshness_reason = (f"posted {j.posted_at} within {max_age} days"
                            if cutoff and posted else
                            "no parseable posted date; freshness not checked"
                            if cutoff else "freshness filter disabled")
        add_example("matched", f"{j.job_id} ({j.title!r}): "
                    f"title pattern {include_pattern!r}; {location_reason}; "
                    f"{freshness_reason}")
        kept.append(j)

    print(f"  prefilter: {len(jobs)} -> {len(kept)} "
          f"(dropped title={stats['title']} location={stats['location']} stale={stats['age']})")
    for category, count in (
            ("title", stats["title"]), ("location", stats["location"]),
            ("age", stats["age"]), ("matched", len(kept))):
        if not count:
            continue
        label = "stale" if category == "age" else category
        print(f"  prefilter {label}: {count}")
        for example in examples[category]:
            print(f"    e.g. {example}")
    return kept
