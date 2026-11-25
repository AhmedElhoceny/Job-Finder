import logging
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from pipeline.nodes import (
    nuextract_node,
    gemini_synthesizer_node,
    scrape_bayt_node,
)
from pipeline.state import CVPipelineState

logger = logging.getLogger(__name__)


def build_job_pipeline_graph(checkpointer: Optional[BaseCheckpointSaver] = None):
    """Constructs and compiles the LangGraph Job Pipeline.

    Graph Architecture:
    START -> extract_with_nuextract -> synthesize_keywords_with_gemini -> scrape_bayt_jobs -> END
    """
    workflow = StateGraph(CVPipelineState)

    # 1. Register Nodes
    workflow.add_node("extract_with_nuextract", nuextract_node)
    workflow.add_node("synthesize_keywords_with_gemini", gemini_synthesizer_node)
    workflow.add_node("scrape_bayt_jobs", scrape_bayt_node)

    # 2. Wire Direct Linear Edges
    workflow.add_edge(START, "extract_with_nuextract")
    workflow.add_edge("extract_with_nuextract", "synthesize_keywords_with_gemini")
    workflow.add_edge("synthesize_keywords_with_gemini", "scrape_bayt_jobs")
    workflow.add_edge("scrape_bayt_jobs", END)

    # 3. Compile Graph with checkpointer
    cp = checkpointer if checkpointer is not None else MemorySaver()
    compiled_pipeline = workflow.compile(checkpointer=cp)
    return compiled_pipeline


# Alias for backward compatibility
build_cv_analysis_graph = build_job_pipeline_graph
