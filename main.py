"""Post new Summer 2027 internships from the upstream JSON feed to Discord."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


FEED_URL = (
    "https://raw.githubusercontent.com/zshah101/"
    "Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/"
    "main/docs/api/jobs.json"
)
TARGET_SEASON = "Summer 2027"
ALLOWED_CATEGORIES = {"Software", "Data & ML/AI", "Security"}
STATE_FILE = Path(__file__).parent / "data" / "posted_jobs.json"
REQUEST_TIMEOUT_SECONDS = 30

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class FeedError(RuntimeError):
    """Raised when the internship feed cannot be read or validated."""


class StateError(RuntimeError):
    """Raised when the local posted-job state is invalid."""


def fetch_jobs() -> list[dict[str, Any]]:
    """Fetch and validate the feed's top-level jobs array."""
    try:
        response = requests.get(FEED_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise FeedError(f"Could not fetch or decode the internship feed: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise FeedError("The internship feed is missing a valid 'jobs' array")

    return [job for job in payload["jobs"] if isinstance(job, dict)]


def matching_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only valid jobs in the requested season and categories."""
    matches: list[dict[str, Any]] = []
    for index, job in enumerate(jobs):
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id.strip():
            logger.warning("Skipping job %d with a missing or invalid id", index)
            continue

        if job.get("season") != TARGET_SEASON:
            continue
        if job.get("category") not in ALLOWED_CATEGORIES:
            continue
        matches.append(job)

    return matches


def load_state(path: Path | None = None) -> tuple[bool, set[str]]:
    """Return whether the state is initialized and the set of posted IDs."""
    path = path or STATE_FILE
    if not path.exists():
        return False, set()

    try:
        with path.open(encoding="utf-8") as state_file:
            state = json.load(state_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Could not read {path}: {exc}") from exc

    if not isinstance(state, dict):
        raise StateError(f"{path} must contain a JSON object")

    posted_ids = state.get("posted_job_ids", [])
    initialized = state.get("initialized", False)
    if not isinstance(initialized, bool) or not isinstance(posted_ids, list):
        raise StateError(f"{path} has invalid state fields")
    if not all(isinstance(job_id, str) and job_id for job_id in posted_ids):
        raise StateError(f"{path} contains an invalid posted job ID")

    return initialized, set(posted_ids)


def save_state(path: Path, posted_ids: set[str], initialized: bool = True) -> None:
    """Persist state in a small, human-readable JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as state_file:
            json.dump(
                {
                    "initialized": initialized,
                    "posted_job_ids": sorted(posted_ids),
                },
                state_file,
                indent=2,
            )
            state_file.write("\n")
    except OSError as exc:
        raise StateError(f"Could not write {path}: {exc}") from exc


def optional_text(job: dict[str, Any], field: str) -> str | None:
    """Return a clean string field, or None when it is absent/malformed."""
    value = job.get(field)
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    logger.warning("Job %s has an invalid %s field; omitting it", job.get("id"), field)
    return None


def build_embed(job: dict[str, Any]) -> dict[str, Any]:
    """Build a Discord embed from the fields supplied by the feed."""
    title = optional_text(job, "title") or "New internship"
    application_url = optional_text(job, "url")
    company = optional_text(job, "company")

    embed: dict[str, Any] = {
        "title": title,
        "color": 0x5865F2,
        "fields": [],
    }
    if application_url:
        embed["url"] = application_url
    if company:
        embed["description"] = company

    for label, field in (
        ("Location", "location"),
        ("Season", "season"),
        ("Category", "category"),
        ("Posted date", "posted_at"),
        ("Sponsorship", "sponsorship"),
    ):
        value = optional_text(job, field)
        if value:
            embed["fields"].append({"name": label, "value": value, "inline": True})

    if application_url:
        embed["fields"].append(
            {"name": "Apply", "value": f"[Open application]({application_url})", "inline": False}
        )

    return embed


def post_job(webhook_url: str, job: dict[str, Any]) -> None:
    """Post one job and raise on a Discord webhook failure."""
    payload = {"embeds": [build_embed(job)]}
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Discord webhook failed for job {job.get('id')}: {exc}") from exc


def main() -> int:
    load_dotenv()

    try:
        initialized, posted_ids = load_state()
        jobs = matching_jobs(fetch_jobs())

        if not initialized:
            save_state(
                STATE_FILE,
                {job["id"] for job in jobs},
                initialized=True,
            )
            logger.info(
                "First run: marked %d existing matching internships as seen; nothing posted",
                len(jobs),
            )
            return 0

        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            raise RuntimeError("DISCORD_WEBHOOK_URL is not set")

        new_jobs = [job for job in jobs if job["id"] not in posted_ids]
        logger.info("Found %d new matching internship(s)", len(new_jobs))

        for job in new_jobs:
            post_job(webhook_url, job)
            posted_ids.add(job["id"])
            save_state(STATE_FILE, posted_ids)
            logger.info("Posted and recorded %s", job["id"])

    except (FeedError, StateError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
