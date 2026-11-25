import argparse
import json
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pipeline.graph import build_cv_analysis_graph
from pipeline.state import CVPipelineState

console = Console()


def render_node_output(node_name: str, node_output: dict):
    """Renders formatted UI components in terminal as LangGraph nodes execute."""
    if node_name == "extract_with_nuextract":
        ne = node_output.get("nuextract_data")
        if ne:
            table = Table(
                title="Node 1: Hugging Face Extraction (nimendraai/NuExtract-tiny-Resume-Data-Extractor)",
                border_style="magenta",
            )
            table.add_column("Property", style="bold magenta", width=22)
            table.add_column("Extracted Entity", style="white")

            table.add_row("Detected Name", ne.get("name") or "N/A")
            table.add_row("Email", ne.get("email") or "N/A")
            table.add_row("Phone", ne.get("phone") or "N/A")
            if ne.get("website"):
                table.add_row("Website / Profile", ne.get("website"))
            table.add_row(
                "Verified Skills (NuExtract)",
                ", ".join(ne.get("skills", [])) if ne.get("skills") else "None",
            )
            if ne.get("experience"):
                exp_list = [
                    f"• [bold]{e.get('title')}[/bold] @ {e.get('company')} ({e.get('duration')})"
                    for e in ne.get("experience", [])
                    if e.get("title") or e.get("company")
                ]
                table.add_row("Experience Timeline", "\n".join(exp_list))
            if ne.get("education"):
                edu_list = [
                    f"• {ed.get('degree')} - {ed.get('institution')} ({ed.get('year')})"
                    for ed in ne.get("education", [])
                    if ed.get("degree") or ed.get("institution")
                ]
                table.add_row("Education", "\n".join(edu_list))

            console.print(table)
        else:
            console.print("[dim yellow]Node 1: NuExtract completed or skipped.[/dim yellow]")

    elif node_name == "synthesize_keywords_with_gemini":
        # 1. Candidate Overview
        overview = Table(title="Candidate Assessment", border_style="cyan")
        overview.add_column("Property", style="bold cyan")
        overview.add_column("Value", style="white")

        overview.add_row("Candidate Name", node_output.get("candidate_name", ""))
        overview.add_row("Seniority Level", f"[bold yellow]{node_output.get('seniority_level', '')}[/bold yellow]")
        overview.add_row("Estimated Experience", f"{node_output.get('estimated_years_of_experience', 0):.1f} years")
        overview.add_row("Target Roles", ", ".join(node_output.get("target_roles", [])))
        console.print(overview)

        # 2. Main Search Keywords (The Primary Deliverable)
        keywords_table = Table(
            title="★ MAIN SEARCH KEYWORDS (Synthesized for Job Scrapers)",
            border_style="bold green",
        )
        keywords_table.add_column("#", width=3, style="dim")
        keywords_table.add_column("Search Keyword", style="bold green")

        for idx, kw in enumerate(node_output.get("search_keywords", []), 1):
            keywords_table.add_row(str(idx), kw)
        console.print(keywords_table)

        # 3. Formatted Search Queries
        queries_table = Table(
            title="Formulated Job Search Queries (Ready for Job Board Search Bars)",
            border_style="yellow",
        )
        queries_table.add_column("#", width=3, style="dim")
        queries_table.add_column("Search Query String", style="bold yellow")

        for idx, q in enumerate(node_output.get("search_queries", []), 1):
            queries_table.add_row(str(idx), q)
        console.print(queries_table)

        # 4. Filters & Negatives
        filter_table = Table(title="Keyword Filter Matrix", border_style="blue")
        filter_table.add_column("Filter Type", style="bold")
        filter_table.add_column("Keywords")

        filter_table.add_row("[cyan]Core Tech Stack[/cyan]", ", ".join(node_output.get("core_skills", [])))
        filter_table.add_row("[cyan]Secondary Tools[/cyan]", ", ".join(node_output.get("secondary_skills", [])))
        if node_output.get("negative_keywords"):
            filter_table.add_row("[red]Negative Keywords (Excluded)[/red]", ", ".join(node_output.get("negative_keywords", [])))
        console.print(filter_table)

        # 5. Summary
        if node_output.get("professional_summary"):
            console.print(
                Panel(
                    node_output.get("professional_summary"),
                    title="[bold cyan]Professional Elevator Pitch[/bold cyan]",
                    border_style="cyan",
                )
            )

    elif node_name == "scrape_bayt_jobs":
        jobs = node_output.get("discovered_jobs", [])
        
        # Summary counts by board
        board_counts: dict[str, int] = {}
        for j in jobs:
            src = j.get("source", "Other")
            board_counts[src] = board_counts.get(src, 0) + 1
        summary_chips = " | ".join([f"[bold yellow]{src}:[/bold yellow] {cnt}" for src, cnt in board_counts.items()])

        table = Table(
            title=f"Node 3: Live Vacancies Discovered (< 1 Month Old) — Total: {len(jobs)} jobs\n{summary_chips}",
            border_style="bold green",
        )
        table.add_column("#", width=3, style="dim")
        table.add_column("Platform", style="magenta", width=16)
        table.add_column("Job Title", style="bold green", max_width=32)
        table.add_column("Company", style="white", max_width=20)
        table.add_column("Location", style="cyan", max_width=18)
        table.add_column("Matched Term", style="yellow")
        table.add_column("Posted", style="dim", width=12)

        for idx, job in enumerate(jobs, 1):
            table.add_row(
                str(idx),
                job.get("source", ""),
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("matched_keyword", ""),
                job.get("date_posted", "") or "Recent",
            )
        console.print(table)


def resolve_cv_file(data_dir: Path, requested_path: str | None = None) -> Path:
    """Finds the candidate CV file, prioritizing any .pdf or .docx placed in data/."""
    if requested_path:
        p = Path(requested_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"Specified CV file not found: {p.resolve()}")

    # 1. Prioritize any PDF in data/
    pdf_files = list(data_dir.glob("*.pdf"))
    if pdf_files:
        return pdf_files[0]

    # 2. Check for Word documents
    docx_files = list(data_dir.glob("*.docx"))
    if docx_files:
        return docx_files[0]

    # 3. Check for user-provided text/markdown files (excluding sample_cv.txt)
    user_txt = [f for f in (list(data_dir.glob("*.txt")) + list(data_dir.glob("*.md"))) if f.name != "sample_cv.txt"]
    if user_txt:
        return user_txt[0]

    # 4. Fallback to sample_cv.txt
    sample = data_dir / "sample_cv.txt"
    if sample.exists():
        return sample

    raise FileNotFoundError(f"No CV document found in {data_dir.resolve()}. Please place your PDF in the data/ folder.")


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Run CV Processing & Multi-Board Scraping LangGraph Pipeline")
    parser.add_argument("--cv", type=str, default=None, help="Path to CV file (.pdf, .docx, .txt)")
    parser.add_argument("--skip-nuextract", action="store_true", help="Skip Hugging Face local model")
    parser.add_argument(
        "--region",
        type=str,
        default="all",
        choices=["all", "global", "mena", "south_asia", "southeast_asia", "east_asia"],
        help="Target geographic region for job boards (default: all)",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    data_dir = project_dir / "data"

    try:
        cv_file = resolve_cv_file(data_dir, args.cv)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    region_map = {
        "all": None,  # All supported boards (including LinkedIn)
        "global": ["LinkedIn Jobs", "LinkedIn Posts"],
        "mena": [
            "Bayt.com", "GulfTalent", "Naukrigulf", "Wuzzuf", "Forasna",
            "Akhtaboot", "Tanqeeb", "ReKrute", "Emploitic", "Dubizzle",
        ],
        "south_asia": [
            "Naukri", "Foundit", "Internshala", "Rozee", "Bdjobs",
        ],
        "southeast_asia": [
            "JobStreet", "JobsDB", "Kalibrr", "JobThai", "VietnamWorks",
            "Glints", "MyCareersFuture",
        ],
        "east_asia": [
            "51job", "Zhaopin", "Boss Zhipin", "Saramin", "JobKorea",
            "104 Job Bank", "Doda", "Mynavi",
        ],
    }
    selected_boards = region_map.get(args.region)

    console.print(
        Panel.fit(
            "[bold cyan]Global Job Finder Pipeline (LangGraph Architecture)[/bold cyan]\n"
            "Node 1: Hugging Face (nimendraai/NuExtract-tiny-Resume-Data-Extractor)\n"
            "Node 2: Google Gemini Free LLM (Keyword & Strategy Synthesizer)\n"
            "Node 3: Multi-Board Scraper (32 Portals & Streams: LinkedIn + MENA + Asia)\n"
            "• Global / LinkedIn: LinkedIn Jobs (formal listings), LinkedIn Posts (recruiter updates)\n"
            "• MENA: Bayt, GulfTalent, Naukrigulf, Wuzzuf, Forasna, Akhtaboot, Tanqeeb, ReKrute, Emploitic, Dubizzle\n"
            "• South Asia: Naukri, Foundit, Internshala, Rozee.pk, Bdjobs\n"
            "• Southeast Asia: JobStreet, JobsDB, Kalibrr, JobThai, VietnamWorks, Glints, MyCareersFuture\n"
            "• East Asia: 51job, Zhaopin, BOSS Zhipin, Saramin, JobKorea, 104 Job Bank, Doda, Mynavi\n"
            "Date Range Filter: Strictly <= 1 Month Old (Excludes stale jobs)\n"
            f"[bold green]Target CV:[/bold green] [white]{cv_file.name}[/white] ([dim]{cv_file.resolve()}[/dim])",
            border_style="cyan",
        )
    )

    # 1. Compile Graph
    pipeline = build_cv_analysis_graph()

    # 2. Prepare initial state
    initial_state: CVPipelineState = {
        "cv_path": str(cv_file),
        "skip_nuextract": args.skip_nuextract,
        "enabled_boards": selected_boards,
    }

    thread_id = str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": thread_id}}

    console.print(f"[dim]Initialized LangGraph session: {thread_id}[/dim]\n")

    # 3. Stream StateGraph execution node-by-node
    final_state = {}
    for event in pipeline.stream(initial_state, config=config):
        for node_name, node_output in event.items():
            render_node_output(node_name, node_output)
            final_state.update(node_output)

    profile_path = Path("data/cv_profile.json")
    jobs_path = Path("data/discovered_jobs.json")
    latest_path = Path("data/latest_run_jobs.json")
    db_path = Path("data/jobs.db")
    discovered_jobs = final_state.get("discovered_jobs", [])
    new_count = final_state.get("newly_added_count", 0)

    console.print(
        f"\n[bold green]✓ Pipeline Execution Complete![/bold green]\n"
        f"• Profile & Keywords: [bold cyan]{profile_path}[/bold cyan]\n"
        f"• Cumulative Jobs JSON: [bold cyan]{jobs_path}[/bold cyan] ([bold green]{len(discovered_jobs)}[/bold green] total merged, [bold yellow]+{new_count} brand-new[/bold yellow])\n"
        f"• Latest Run Batch: [bold cyan]{latest_path}[/bold cyan]\n"
        f"• SQLite Database: [bold cyan]{db_path}[/bold cyan] (table: jobs)\n"
    )


if __name__ == "__main__":
    main()
