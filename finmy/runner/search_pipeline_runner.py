"""Search-driven reconstruction using the shared search agent only."""
from __future__ import annotations

import copy
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def build_search_query(main_input: str, keywords: List[str]) -> str:
    return f"{main_input} \n\nkeywords: {' '.join(keywords)}"


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def _create_pipeline(config: Dict[str, Any]):
    from finmy.pipeline import FinmyPipeline
    return FinmyPipeline(config)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_search_pipeline(
    config: Dict[str, Any],
    main_input: str,
    keywords: List[str],
    save_dir: str | Path,
    search_task=None,
    search_dependencies=None,
) -> Dict[str, Any]:
    from finmy.reconstruction_scope import read_reconstruction
    from finmy.runner.event_followup_config import normalize_followup_config
    from finmy.runner.enhanced_subject_search import agent_search_config
    scope = read_reconstruction(config)
    search_config = agent_search_config(config)
    if scope["mode"] != "event":
        return _run_person_draft_followup(
            normalize_followup_config(config), main_input, keywords, save_dir,
            search_task=search_task, search_dependencies=search_dependencies,
        )
    from finmy.search.pipeline import run_search

    task = search_task or dict(target_type="event", target_name=main_input,
                               query_text=main_input, key_words=keywords)
    search_result = run_search(
        task, root=Path(save_dir) / "search", task_id="task",
        config=search_config, **(search_dependencies or {}),
    )
    path = search_result.get("builder_input_path")
    if not path:
        return {**search_result, "pipeline_result": None, "save_dir": str(save_dir)}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = [sample for sample in payload.get("samples", [])
               if sample.get("content", "").strip()]
    contents = [sample["content"] for sample in samples]
    if not contents:
        return {**search_result, "pipeline_result": None, "save_dir": str(save_dir)}
    # The search handoff already applied its material budget. Preserve its exact
    # bodies and map provenance to the new pipeline's positional sample IDs.
    build_config = copy.deepcopy(config)
    registry = payload["user_query"].get("extras", {}).get("source_registry", {})
    if registry:
        build_config["source_registry"] = {
            f"saved_{index}": copy.deepcopy(registry[sample["raw_data_id"]])
            for index, sample in enumerate(samples)
            if sample["raw_data_id"] in registry
        }
    pipeline = _create_pipeline(build_config)
    result = pipeline.lm_build_pipeline_with_contents(
        contents=contents, query_text=payload["user_query"]["query_text"],
        key_words=payload["user_query"].get("key_words", []),
    )
    return {**search_result, "all_text_content": contents,
            "limited_content_count": len(contents), "pipeline_result": result,
            "save_dir": str(save_dir)}


def _run_person_draft_followup(config, main_input, keywords, save_dir,
                               *, search_task=None, search_dependencies=None):
    """Acquire through the agent, then build and optionally enrich its events."""
    from finmy.reconstruction_scope import read_reconstruction
    from finmy.runner.source_documents import prepare_documents
    from finmy.runner.context_budget import allocate_context
    from finmy.runner.event_followup_config import followup_enabled
    from finmy.runner.event_refinement import build_with_draft_event_followup
    from finmy.runner.enhanced_subject_search import collect_enhanced_sources

    keywords = keywords or []
    config = copy.deepcopy(config)
    reconstruction = read_reconstruction(config)
    target = Path(save_dir)
    target.mkdir(parents=True, exist_ok=True)
    usage = {}
    acquired = collect_enhanced_sources(
        main_input, keywords, reconstruction["subject"], config, target,
        progress=logger.info, usage=usage, dependencies=search_dependencies,
        task=search_task,
    )
    from finmy.runner.search_status import has_search_material, incomplete_search_result, record_search_coverage
    if not has_search_material(acquired):
        return incomplete_search_result(acquired, target)
    record_search_coverage(acquired, target)
    documents = acquired["documents"]
    if acquired.get("storyline_plan"):
        config["storyline_plan"] = copy.deepcopy(acquired["storyline_plan"])
        config.setdefault("all_content_config", {})["allocation_strategy"] = "event"
    contents = [doc["raw_text"] for doc in documents]
    _write_json(target / f"All_Text_Content_{_timestamp()}.json", contents)
    documents = prepare_documents(documents, main_input, keywords, config, target)
    packed = allocate_context(documents, [], config, include_metadata=True)
    _write_json(target / "context_budget_report.json", packed["report"])
    _write_json(target / "builder_input_contents.json", packed["contents"])
    if not packed["contents"]:
        raise ValueError("No relevant source text fits the initial context budget.")
    from finmy.subject_graph.runner import with_source_registry
    config = with_source_registry(config, documents, packed)
    record_search_coverage(acquired, target, builder_status="running")
    try:
        if followup_enabled(config):
            result, directory = build_with_draft_event_followup(packed["contents"], main_input, keywords,
                config, target, documents=documents, usage=usage,
                progress=logger.info)
        else:
            from finmy.subject_graph.runner import build_from_contents
            result, directory = build_from_contents(packed["contents"], main_input, keywords, config)
    except Exception as error:
        try:
            record_search_coverage(acquired, target,
                builder_directory=getattr(error, "builder_directory", None),
                builder_status="failed", builder_error=error)
        except OSError:
            logger.exception("Could not update Builder failure status")
        raise
    coverage = record_search_coverage(acquired, target, builder_directory=directory,
        builder_status="completed" if result is not None else "failed")
    final_input = json.loads((target / "builder_input_contents.json").read_text(encoding="utf-8"))
    return {**coverage, "all_text_content": contents, "search_query": build_search_query(main_input, keywords),
            "limited_content_count": len(final_input), "pipeline_result": result,
            "save_dir": str(target), "builder_save_dir": directory}
