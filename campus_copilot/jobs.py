"""Job discovery from public job-board APIs (no HTML scraping of sites that forbid it)."""
import hashlib
import html
import logging
import re

import requests

from . import store

log = logging.getLogger("copilot")
UA = {"User-Agent": "campus-copilot/1.0 (personal job tracker)"}


def _clean(s, n=1500):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def _job(title, company, location, url, desc):
    return {"key": hashlib.sha1(url.encode()).hexdigest(), "title": title, "company": company,
            "location": location, "url": url, "desc": _clean(desc)}


def _greenhouse(src):
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{src['board']}/jobs",
                     params={"content": "true"}, headers=UA, timeout=30)
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        yield _job(j["title"], src["company"], (j.get("location") or {}).get("name", ""),
                   j["absolute_url"], j.get("content", ""))


def _lever(src):
    r = requests.get(f"https://api.lever.co/v0/postings/{src['board']}", params={"mode": "json"},
                     headers=UA, timeout=30)
    r.raise_for_status()
    for j in r.json():
        yield _job(j["text"], src["company"], (j.get("categories") or {}).get("location", ""),
                   j["hostedUrl"], j.get("descriptionPlain", ""))


def _remotive(src):
    r = requests.get("https://remotive.com/api/remote-jobs", params={"search": src["search"]},
                     headers=UA, timeout=30)
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        yield _job(j["title"], j["company_name"], j.get("candidate_required_location", "Remote"),
                   j["url"], j.get("description", ""))


FETCHERS = {"greenhouse": _greenhouse, "lever": _lever, "remotive": _remotive}


def fetch_new(cfg):
    jc = cfg["jobs"]
    inc = [w.lower() for w in jc["title_include"]]
    exc = [w.lower() for w in jc["title_exclude"]]
    found = {}
    for src in jc["sources"]:
        try:
            for job in FETCHERS[src["type"]](src):
                t = job["title"].lower()
                if any(w in t for w in exc) or not any(w in t for w in inc):
                    continue
                if not store.is_seen(job["key"]):
                    found[job["key"]] = job
        except Exception as e:  # noqa: BLE001
            log.warning("Source %s failed: %s", src, e)
    return list(found.values())[: jc["max_new_per_run"]]
