import logging
from pathlib import Path
from typing import Any

from agents.cv_analyzer import CVAnalyzer
from core.nuextract_extractor import get_extractor
from pipeline.state import CVPipelineState

logger = logging.getLogger(__name__)


def nuextract_node(state: CVPipelineState) -> dict[str, Any]:
    """LangGraph Node 1: Ingests the CV document and extracts ground truth facts

    using Hugging Face model: nimendraai/NuExtract-tiny-Resume-Data-Extractor.
    """
    cv_path_str = state.get("cv_path")

    # 1. Resolve CV file path
    if not cv_path_str:
        default_data = Path("data")
        pdf_files = list(default_data.glob("*.pdf"))
        docx_files = list(default_data.glob("*.docx"))
        user_txt = [f for f in default_data.glob("*.txt") if f.name != "sample_cv.txt"]

        if pdf_files:
            cv_path_str = str(pdf_files[0])
        elif docx_files:
            cv_path_str = str(docx_files[0])
        elif user_txt:
            cv_path_str = str(user_txt[0])
        elif (default_data / "sample_cv.txt").exists():
            cv_path_str = str(default_data / "sample_cv.txt")
        else:
            return {
                "errors": ["No CV file provided or found in data/ directory."],
                "current_stage": "cv_ingestion_failed",
            }

    cv_path = Path(cv_path_str)
    if not cv_path.exists():
        return {
            "errors": [f"CV file not found: {cv_path.resolve()}"],
            "current_stage": "cv_not_found",
        }

    # 2. Extract raw text from PDF/DOCX/TXT
    logger.info(f"[Node 1: NuExtract] Extracting text from document: {cv_path.name}")
    try:
        cv_text = CVAnalyzer.extract_text(cv_path)
    except Exception as e:
        return {
            "errors": [f"Failed to read CV document: {e}"],
            "current_stage": "cv_extraction_failed",
        }

    # 3. Run Hugging Face NuExtract model (unless skipped)
    skip_nuextract = state.get("skip_nuextract", False)
    nuextract_data = None

    if not skip_nuextract:
        logger.info("[Node 1: NuExtract] Running Hugging Face model: nimendraai/NuExtract-tiny-Resume-Data-Extractor...")
        try:
            extractor = get_extractor()
            result = extractor.extract(cv_text)
            nuextract_data = result.model_dump()
            logger.info(
                f"[Node 1: NuExtract] Successfully extracted {len(nuextract_data.get('skills', []))} skills "
                f"and {len(nuextract_data.get('experience', []))} work experiences for '{nuextract_data.get('name')}'."
            )
        except Exception as e:
            logger.warning(f"[Node 1: NuExtract] NuExtract extraction encountered: {e}")
            nuextract_data = None

    return {
        "cv_path": str(cv_path),
        "cv_text": cv_text,
        "nuextract_data": nuextract_data,
        "current_stage": "nuextract_processed",
        "status_messages": [
            f"Node 1 completed: Extracted raw text and processed with Hugging Face NuExtract model."
        ],
    }
