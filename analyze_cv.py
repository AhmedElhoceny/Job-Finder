import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agents.cv_analyzer import CVAnalyzer
from core.models.cv_analysis import CVAnalysisResult

console = Console()

SAMPLE_CV_TEXT = """
Ahmed Elhoceny
Cairo, Egypt | ahmed.elhoceny@example.com | +20 100 000 0000
LinkedIn: linkedin.com/in/ahmed-elhoceny | GitHub: github.com/ahmedelhoceny

PROFESSIONAL SUMMARY
Senior Software Engineer with 6+ years of experience specializing in Python, FastAPI, Django,
and Cloud Microservices architectures. Proven track record in designing resilient distributed systems,
optimizing high-throughput databases (PostgreSQL, Redis), and implementing production LLM / AI integrations.
Experienced with Docker, Kubernetes, CI/CD pipelines, and AWS cloud solutions.

CORE TECHNICAL SKILLS
- Languages: Python, JavaScript/TypeScript, SQL, Bash
- Backend Frameworks: FastAPI, Django, Flask, Celery, REST APIs, GraphQL
- Databases & Caching: PostgreSQL, Redis, MongoDB, SQLAlchemy
- Cloud & DevOps: Docker, Kubernetes, AWS (EC2, S3, RDS, Lambda), GitHub Actions, CI/CD
- AI / LLM Engineering: LangChain, Google Gemini API, OpenAI API, Vector Databases (ChromaDB, Pinecone)
- Architecture & Practices: Microservices, Event-Driven Architecture, Unit Testing (pytest), Agile/Scrum

PROFESSIONAL EXPERIENCE
Senior Backend Engineer | CloudScale Solutions (Remote) | 2022 - Present
- Architected and built high-performance microservices using FastAPI and PostgreSQL handling 2M+ requests daily.
- Integrated LLM agent pipelines using LangChain and Gemini API for automated document processing, reducing manual workload by 70%.
- Designed Celery distributed task queuing with Redis for asynchronous background processing.
- Orchestrated container deployment with Docker and Kubernetes on AWS EKS with 99.9% uptime.

Software Engineer | FinTech Systems (Cairo, Egypt) | 2019 - 2022
- Developed secure payment gateway integrations and transaction ledgers using Django and PostgreSQL.
- Optimized database query bottlenecks, cutting p95 response latencies from 450ms to 95ms.
- Built automated CI/CD deployment pipelines using GitHub Actions.

EDUCATION
B.Sc. in Computer Science | Cairo University (2015 - 2019)
"""


def find_cv_file(data_dir: Path) -> Path | None:
    """Checks common filenames in data/ for candidate CV."""
    candidates = [
        "cv.pdf", "resume.pdf", "CV.pdf", "Resume.pdf",
        "cv.docx", "resume.docx", "cv.txt", "resume.txt",
        "cv.md", "resume.md",
    ]
    for name in candidates:
        candidate_path = data_dir / name
        if candidate_path.exists():
            return candidate_path

    # Fallback to any .pdf, .docx, .txt in data/
    for ext in ("*.pdf", "*.docx", "*.txt", "*.md"):
        matches = list(data_dir.glob(ext))
        if matches:
            return matches[0]
    return None


def display_results(result: CVAnalysisResult, saved_path: Path):
    """Renders a beautiful summary of the extracted CV parameters."""
    console.print(
        Panel.fit(
            f"[bold green]CV Analysis Complete: {result.candidate_name}[/bold green]\n"
            f"[dim]Saved structured search profile to: {saved_path}[/dim]",
            border_style="green",
        )
    )

    # 1. NuExtract HF Model Ground Truth Table (if available)
    if result.nuextract_raw and result.nuextract_raw.skills:
        ne = result.nuextract_raw
        nuextract_table = Table(
            title="HuggingFace Model Extraction (nimendraai/NuExtract-tiny-Resume-Data-Extractor)",
            border_style="magenta",
        )
        nuextract_table.add_column("Field", style="bold magenta", width=20)
        nuextract_table.add_column("Extracted Entity", style="white")

        nuextract_table.add_row("Detected Name", ne.name or "N/A")
        nuextract_table.add_row("Email / Contact", f"{ne.email or ''} | {ne.phone or ''}".strip(" |"))
        if ne.website:
            nuextract_table.add_row("Website / Profile", ne.website)
        nuextract_table.add_row(
            "Verified Skills (NuExtract)",
            ", ".join(ne.skills) if ne.skills else "None",
        )
        if ne.experience:
            exp_strings = [
                f"[bold]{e.title}[/bold] @ {e.company} ({e.duration})"
                for e in ne.experience
                if e.title or e.company
            ]
            nuextract_table.add_row("Work Experience", "\n".join(exp_strings))
        if ne.education:
            edu_strings = [
                f"{ed.degree} - {ed.institution} ({ed.year})"
                for ed in ne.education
                if ed.degree or ed.institution
            ]
            nuextract_table.add_row("Education", "\n".join(edu_strings))

        console.print(nuextract_table)

    # 2. Candidate Overview Table (Synthesized)
    overview_table = Table(title="Candidate Assessment & Search Profile", border_style="cyan")
    overview_table.add_column("Property", style="bold cyan")
    overview_table.add_column("Value", style="white")

    overview_table.add_row("Name", result.candidate_name)
    overview_table.add_row("Email", result.contact_email or "Not detected")
    overview_table.add_row("Phone", result.contact_phone or "Not detected")
    overview_table.add_row("Location", result.location or "Not specified")
    overview_table.add_row("Seniority Level", f"[bold yellow]{result.seniority_level}[/bold yellow]")
    overview_table.add_row("Estimated Exp.", f"{result.estimated_years_of_experience:.1f} years")
    overview_table.add_row("Target Roles", ", ".join(result.current_or_target_roles))
    console.print(overview_table)

    # 3. Skills & Domains Table
    skills_table = Table(title="Synthesized Skills & Domains", border_style="blue")
    skills_table.add_column("Category", style="bold cyan")
    skills_table.add_column("Skills", style="white")

    skills_table.add_row("Core Tech Stack", "[bold green]" + ", ".join(result.core_skills) + "[/bold green]")
    skills_table.add_row("Secondary Tools", ", ".join(result.secondary_skills))
    if result.domains_and_industries:
        skills_table.add_row("Domains / Industries", ", ".join(result.domains_and_industries))
    console.print(skills_table)

    # 4. Search Queries Table (Key for Phase 3 Scraper)
    queries_table = Table(
        title="Generated Job Search Queries (Used for Scrapers & Job Boards)",
        border_style="yellow",
    )
    queries_table.add_column("#", style="dim", width=4)
    queries_table.add_column("Target Search Query", style="bold yellow")

    for idx, query in enumerate(result.search_queries, 1):
        queries_table.add_row(str(idx), query)
    console.print(queries_table)

    # 5. Search & Negative Keywords
    kw_table = Table(title="Keyword Filter Matrix", border_style="green")
    kw_table.add_column("Type", style="bold")
    kw_table.add_column("Keywords")

    kw_table.add_row("[green]Target Search Keywords[/green]", ", ".join(result.search_keywords))
    if result.negative_keywords:
        kw_table.add_row("[red]Negative Keywords (Excluded)[/red]", ", ".join(result.negative_keywords))
    console.print(kw_table)

    # 6. Elevator Pitch
    console.print(
        Panel(
            result.professional_summary,
            title="[bold cyan]Professional Elevator Pitch[/bold cyan]",
            border_style="cyan",
        )
    )


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Analyze CV and extract search keywords for Job Finder pipeline.")
    parser.add_argument("--cv", type=str, default=None, help="Path to your CV file (.pdf, .docx, .txt, .md)")
    parser.add_argument("--out", type=str, default="data/cv_profile.json", help="Path to output structured profile JSON")
    parser.add_argument("--skip-nuextract", action="store_true", help="Skip HuggingFace NuExtract local model and use Gemini directly")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    data_dir = project_dir / "data"
    output_path = project_dir / args.out

    analyzer = CVAnalyzer()

    # Determine CV source
    if args.cv:
        cv_path = Path(args.cv)
        if not cv_path.is_absolute():
            cv_path = project_dir / cv_path
        if not cv_path.exists():
            console.print(f"[bold red]Error:[/bold red] CV file not found at: {cv_path}")
            sys.exit(1)
        console.print(f"[cyan]Analyzing provided CV:[/cyan] {cv_path.name}")
        with console.status("[bold cyan]Extracting with NuExtract & analyzing with Gemini...[/bold cyan]"):
            result = analyzer.analyze_file(
                cv_path,
                output_json_path=output_path,
                skip_nuextract=args.skip_nuextract,
            )
    else:
        # Check if user has placed a CV in data/
        cv_path = find_cv_file(data_dir)
        if cv_path:
            console.print(f"[cyan]Auto-detected CV in data directory:[/cyan] {cv_path.name}")
            with console.status("[bold cyan]Extracting with NuExtract & analyzing with Gemini...[/bold cyan]"):
                result = analyzer.analyze_file(
                    cv_path,
                    output_json_path=output_path,
                    skip_nuextract=args.skip_nuextract,
                )
        else:
            # Provide sample CV so the user can test the pipeline immediately
            sample_file = data_dir / "sample_cv.txt"
            sample_file.write_text(SAMPLE_CV_TEXT.strip(), encoding="utf-8")
            console.print(
                Panel(
                    f"No CV file was specified or found in [bold]{data_dir}[/bold].\n\n"
                    f"1. Created a demo template CV at: [bold green]{sample_file.name}[/bold green]\n"
                    f"2. You can place your own CV ([bold white]cv.pdf[/bold white] or [bold white]cv.docx[/bold white]) into [bold]data/[/bold]\n"
                    f"   or run: [bold white]python analyze_cv.py --cv path\\to\\your_cv.pdf[/bold white]\n\n"
                    "Extracting with NuExtract-tiny model and synthesizing with Gemini...",
                    title="[yellow]Running with Sample CV[/yellow]",
                    border_style="yellow",
                )
            )
            with console.status("[bold cyan]Extracting with NuExtract & analyzing with Gemini...[/bold cyan]"):
                result = analyzer.analyze_file(
                    sample_file,
                    output_json_path=output_path,
                    skip_nuextract=args.skip_nuextract,
                )

    display_results(result, output_path)
    console.print("[bold green]Stage 1 Complete! Generated profile is ready for Stage 2 (Job Scraping).[/bold green]\n")


if __name__ == "__main__":
    main()
