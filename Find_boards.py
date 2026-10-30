"""Auto-detect the real ATS + slug for each company in companies.yml.

For every company it tries several slug guesses (the slug you wrote, plus
variants of the company name) on Greenhouse, Lever and Ashby, and keeps
the first one that returns real jobs. Output: companies.verified.yml

Usage:  pip install requests pyyaml
        python find_boards.py
"""
import re
import urllib.parse

import requests
import yaml

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
    "lever": "https://api.lever.co/v0/postings/{s}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{s}",
}


def job_count(ats, data):
    if ats == "lever":
        return len(data) if isinstance(data, list) else 0
    return len(data.get("jobs", [])) if isinstance(data, dict) else 0


def slug_guesses(c):
    name = re.sub(r"[^a-z0-9 ]", "", c["name"].lower()).strip()
    given = urllib.parse.unquote(c["slug"])
    guesses = [given, given.lower(), name.replace(" ", ""),
               name.replace(" ", "-"), name.replace(" ", "") + "inc",
               name.replace(" ", "") + "hq"]
    out, seen = [], set()
    for g in guesses:
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def try_board(ats, slug):
    try:
        r = requests.get(URLS[ats].format(s=urllib.parse.quote(slug)), timeout=12)
        if r.status_code == 200:
            return job_count(ats, r.json())
    except Exception:
        pass
    return None


def main():
    with open("companies.yaml") as f:
        companies = yaml.safe_load(f)["companies"]

    found, missing, seen = [], [], set()
    for c in companies:
        if c["name"].lower() in seen:
            continue
        seen.add(c["name"].lower())

        # try the ATS you listed first, then the other two
        order = [c["ats"]] + [a for a in URLS if a != c["ats"]]
        hit = None
        for slug in slug_guesses(c):
            for ats in order:
                n = try_board(ats, slug)
                if n is not None:
                    hit = {"ats": ats, "slug": slug, "name": c["name"]}
                    print(f"OK    {c['name']:28} {ats}/{slug} ({n} jobs)")
                    break
            if hit:
                break
        if hit:
            found.append(hit)
        else:
            missing.append(c["name"])
            print(f"MISS  {c['name']}")

    with open("companies.verified.yml", "w") as f:
        yaml.safe_dump({"companies": found}, f, sort_keys=False)
    print(f"\nLive: {len(found)} | Not found: {len(missing)}")
    print("Not found (check careers page manually):", ", ".join(missing))


if __name__ == "__main__":
    main()