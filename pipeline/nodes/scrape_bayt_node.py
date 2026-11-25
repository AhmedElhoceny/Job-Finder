import json
import logging
from pathlib import Path
from typing import Any

from core.database import JobDatabase
from pipeline.state import CVPipelineState
from scrapers.aggregator import MultiBoardJobScraper

logger = logging.getLogger(__name__)


def scrape_jobs_node(state: CVPipelineState) -> dict[str, Any]:
    """LangGraph Node: Scrapes live vacancies across global and regional job boards

    (MENA, South Asia, Southeast Asia, East Asia) based on the synthesized keywords,
    strictly filtering for jobs posted within the last 1 month (<= 30 days).
    """
    search_keywords = state.get("search_keywords", [])
    target_roles = state.get("target_roles", [])
    negative_keywords = state.get("negative_keywords", [])
    enabled_boards = state.get("enabled_boards")

    logger.info("[Node 3: Multi-Board Scraper] Scraping across MENA, South Asia, Southeast Asia, and East Asia job boards...")

    orchestrator = MultiBoardJobScraper(request_delay=1.0)
    filtered_jobs = orchestrator.scrape_all_boards(
        target_roles=target_roles,
        search_keywords=search_keywords,
        negative_keywords=negative_keywords,
        enabled_boards=enabled_boards,  # Defaults to all supported boards
        max_days=30,  # Strictly filter out jobs posted older than 1 month
    )

    serialized_jobs = [j.model_dump() for j in filtered_jobs]

    # 1. Load existing jobs from data/discovered_jobs.json to MERGE instead of overwrite
    json_path = Path("data/discovered_jobs.json")
    existing_jobs_by_url: dict[str, dict] = {}
    if json_path.exists():
        try:
            old_data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(old_data, list):
                for item in old_data:
                    if isinstance(item, dict) and "url" in item:
                        existing_jobs_by_url[item["url"]] = item
        except Exception as e:
            logger.warning(f"Could not read existing discovered_jobs.json: {e}")

    # Count how many are completely brand-new
    brand_new_count = 0
    for job in serialized_jobs:
        url = job.get("url")
        if url:
            if url not in existing_jobs_by_url:
                brand_new_count += 1
            existing_jobs_by_url[url] = job  # Merge / update latest data

    # Cumulative merged list
    cumulative_jobs = list(existing_jobs_by_url.values())
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(cumulative_jobs, indent=2), encoding="utf-8")

    # Save latest run batch separately for quick reference
    latest_run_path = Path("data/latest_run_jobs.json")
    latest_run_path.write_text(json.dumps(serialized_jobs, indent=2), encoding="utf-8")

    # Also save to bayt_jobs.json for backward compatibility if Bayt jobs exist
    bayt_only = [j for j in cumulative_jobs if j.get("source") == "Bayt.com"]
    if bayt_only:
        Path("data/bayt_jobs.json").write_text(json.dumps(bayt_only, indent=2), encoding="utf-8")

    # Also save to linkedin_results.json if LinkedIn jobs or posts exist
    linkedin_only = [j for j in cumulative_jobs if "LinkedIn" in j.get("source", "")]
    if linkedin_only:
        Path("data/linkedin_results.json").write_text(json.dumps(linkedin_only, indent=2, ensure_ascii=False), encoding="utf-8")

    # Breakdown by source for logging
    counts_by_source = {}
    for j in cumulative_jobs:
        src = j.get("source", "Unknown")
        counts_by_source[src] = counts_by_source.get(src, 0) + 1

    summary_str = ", ".join([f"{src}: {cnt}" for src, cnt in counts_by_source.items()])

    return {
        "discovered_jobs": cumulative_jobs,
        "newly_added_count": brand_new_count,
        "bayt_jobs": bayt_only,
        "current_stage": "jobs_scraped",
        "status_messages": [
            f"Node 3 completed: Merged {brand_new_count} brand-new vacancies into cumulative file ({len(cumulative_jobs)} total in database: {summary_str})."
        ],
    }


# Alias for backward compatibility
scrape_bayt_node = scrape_jobs_node
