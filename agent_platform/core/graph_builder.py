"""Agent relationship graph inference via static analysis and runtime detection.

Uses Python's ast module to scan orchestrator/graph.py and agent source files
for cross-agent references, LangGraph add_node/add_edge calls, and
inter-agent imports. Also supports runtime edge recording.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Any

from agent_platform.core.agent_manager import _detect_llm_usage
from agent_platform.db.client import get_database
from agent_platform.db.repositories.agent_repo import AgentRepository
from agent_platform.db.repositories.relationship_repo import RelationshipRepository

logger = logging.getLogger(__name__)


async def build_static_graph(agent_id: str) -> list[dict[str, Any]]:
    """Analyse an uploaded agent package and store detected inter-agent edges.

    Scans orchestrator/graph.py and all agent_*/ source files for:
    - add_node / add_edge calls referencing other agent modules
    - import statements crossing agent folder boundaries
    - String literals naming other agent folders

    Relationships are stored in the agent_relationships collection.
    Returns the list of detected edges.
    """
    db = get_database()
    agent_repo = AgentRepository(db)
    rel_repo = RelationshipRepository(db)

    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        return []

    base = Path(agent["upload_path"])
    root_dirs = [d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")]
    root_dir = root_dirs[0] if root_dirs else base

    agent_folders: list[str] = agent.get("agent_folders", [])
    if not agent_folders:
        return []

    folder_set = set(agent_folders)
    edges: list[dict[str, Any]] = []

    # Map folder names to a pseudo ID scheme: <agent_id>:<folder_name>
    def _make_sub_id(folder: str) -> str:
        return f"{agent_id}:{folder}"

    for py_file in root_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except SyntaxError:
            continue

        rel_parts = py_file.relative_to(root_dir).parts
        owning = rel_parts[0] if rel_parts else None

        for node in ast.walk(tree):
            # add_edge("source", "target") in orchestrator graph
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "add_edge":
                    str_args = [
                        a.value
                        for a in node.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    ]
                    if len(str_args) >= 2:
                        src, tgt = str_args[0], str_args[1]
                        # Only record if both refer to known agent folders
                        src_match = _find_folder(src, folder_set)
                        tgt_match = _find_folder(tgt, folder_set)
                        if src_match and tgt_match and src_match != tgt_match:
                            edges.append({
                                "source": src_match,
                                "target": tgt_match,
                                "type": "delegates",
                            })

            # import agent_beta / from agent_alpha import ...
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                elif isinstance(node, ast.Import):
                    modules.extend(a.name for a in node.names)
                for mod in modules:
                    top = mod.split(".")[0]
                    if top in folder_set and top != owning:
                        edges.append({
                            "source": owning or "orchestrator",
                            "target": top,
                            "type": "imports",
                        })

        # Regex fallback for string references
        for folder in folder_set:
            if owning and folder != owning:
                if re.search(rf"\b{re.escape(folder)}\b", content):
                    edge = {"source": owning, "target": folder, "type": "calls"}
                    if edge not in edges:
                        edges.append(edge)

    # Deduplicate
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        key = (e["source"], e["target"], e["type"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    # Persist edges
    for e in unique:
        await rel_repo.upsert_relationship({
            "source_agent_id": _make_sub_id(e["source"]),
            "target_agent_id": _make_sub_id(e["target"]),
            "relationship_type": e["type"],
            "detected_via": "static_analysis",
            "confidence": 0.85,
        })

    logger.info("Static analysis for agent %s found %d edges", agent_id, len(unique))
    return unique


def _find_folder(name: str, folder_set: set[str]) -> str | None:
    """Match a node/edge name to a known agent folder."""
    if name in folder_set:
        return name
    for f in folder_set:
        if name.startswith(f) or f.startswith(name):
            return f
    return None


async def record_runtime_edge(
    source_agent_id: str, target_agent_id: str
) -> None:
    """Record an edge detected at runtime (e.g. agent A invoking agent B)."""
    db = get_database()
    rel_repo = RelationshipRepository(db)
    await rel_repo.upsert_relationship({
        "source_agent_id": source_agent_id,
        "target_agent_id": target_agent_id,
        "relationship_type": "calls",
        "detected_via": "runtime",
        "confidence": 1.0,
    })


def _get_folder_nodes(folder_path: Path) -> list[str]:
    """Extract LangGraph add_node names from an agent folder's Python files."""
    nodes: list[str] = []
    seen: set[str] = set()
    for py_file in folder_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "add_node"
                    and node.args
                ):
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        name = first_arg.value
                        if name not in seen:
                            seen.add(name)
                            nodes.append(name)
    return nodes


def _get_orchestrator_pipeline_edges(
    orch_path: Path, folder_set: set[str]
) -> list[dict[str, str]]:
    """Scan orchestrator files for add_edge calls to find agent-to-agent pipeline flow."""
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for py_file in orch_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "add_edge":
                    str_args = [
                        a.value for a in node.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    ]
                    if len(str_args) >= 2:
                        src_m = _find_folder(str_args[0], folder_set)
                        tgt_m = _find_folder(str_args[1], folder_set)
                        if src_m and tgt_m and src_m != tgt_m and (src_m, tgt_m) not in seen:
                            seen.add((src_m, tgt_m))
                            edges.append({
                                "source": src_m,
                                "target": tgt_m,
                                "label": "output → input",
                                "type": "pipeline",
                            })
    return edges


async def get_team_graph(agent_id: str) -> dict[str, Any]:
    """Return the internal pipeline graph of a team for visualisation.

    Produces an orchestrator node, one node per agent folder with its
    LangGraph pipeline nodes, and edges derived from the orchestrator
    add_edge calls and stored internal_refs.
    """
    db = get_database()
    agent_repo = AgentRepository(db)

    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        return {}

    agent_folders: list[str] = agent.get("agent_folders", [])
    internal_refs: list[dict[str, str]] = agent.get("internal_refs", [])

    # Locate the extracted root dir
    base = Path(agent["upload_path"])
    root_dirs = [
        d for d in base.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name != "logs"
    ]
    root_dir = root_dirs[0] if root_dirs else base

    folder_set = set(agent_folders)

    # Per-agent node lists
    per_agent_nodes: dict[str, list[str]] = {}
    for folder in agent_folders:
        fp = root_dir / folder
        if fp.exists():
            per_agent_nodes[folder] = _get_folder_nodes(fp)

    # Orchestrator-level add_edge calls → pipeline ordering
    orch_path = root_dir / "orchestrator"
    pipeline_edges = _get_orchestrator_pipeline_edges(orch_path, folder_set) if orch_path.exists() else []

    # LLM usage per agent folder (fall back to live scan for older agents)
    llm_by_agent: dict[str, bool] = agent.get("llm_by_agent") or {}
    if not llm_by_agent:
        llm_by_agent = _detect_llm_usage(root_dir, agent_folders)

    # Build node list
    agent_colors = ["#3b82f6", "#06b6d4", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444"]
    nodes: list[dict[str, Any]] = [
        {
            "id": "orchestrator",
            "label": "Orchestrator",
            "type": "orchestrator",
            "sub_nodes": agent_folders,
            "description": "Coordinates and sequences all agents in the pipeline",
        }
    ]
    any_uses_llm = False
    for i, folder in enumerate(agent_folders):
        uses_llm = llm_by_agent.get(folder, False)
        if uses_llm:
            any_uses_llm = True
        nodes.append({
            "id": folder,
            "label": folder.replace("_", " ").title(),
            "type": "agent",
            "color": agent_colors[i % len(agent_colors)],
            "sub_nodes": per_agent_nodes.get(folder, []),
            "uses_llm": uses_llm,
        })

    if any_uses_llm:
        nodes.append({
            "id": "llm",
            "label": "LLM",
            "type": "llm",
            "sub_nodes": [f for f in agent_folders if llm_by_agent.get(f, False)],
            "description": "Large Language Model used by agents for reasoning and generation",
        })

    # Build edge list — prefer scanned orchestrator edges; fall back to internal_refs
    edges: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Orchestrator → each agent (from internal_refs or default)
    agents_mentioned = {r["target"] for r in internal_refs if r.get("source") == "orchestrator"}
    if not agents_mentioned:
        agents_mentioned = set(agent_folders)
    for folder in agent_folders:
        if folder in agents_mentioned:
            pair = ("orchestrator", folder)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                edges.append({"source": "orchestrator", "target": folder, "label": "invokes", "type": "invoke"})

    # Agent-to-agent pipeline (from orchestrator add_edge scans)
    for e in pipeline_edges:
        pair = (e["source"], e["target"])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            edges.append(e)

    # Default sequential pipeline if nothing detected
    if len(edges) <= len(agent_folders) and not pipeline_edges and len(agent_folders) > 1:
        for i in range(len(agent_folders) - 1):
            pair = (agent_folders[i], agent_folders[i + 1])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                edges.append({
                    "source": agent_folders[i],
                    "target": agent_folders[i + 1],
                    "label": "output → input",
                    "type": "pipeline",
                })

    # Agent → LLM edges
    if any_uses_llm:
        for folder in agent_folders:
            if llm_by_agent.get(folder, False):
                edges.append({
                    "source": folder,
                    "target": "llm",
                    "label": "calls",
                    "type": "llm",
                })

    return {
        "team": {
            "id": agent["_id"],
            "name": agent["name"],
            "status": agent.get("status", "idle"),
            "run_count": agent.get("run_count", 0),
            "agent_folders": agent_folders,
            "detected_tools": agent.get("detected_tools", []),
        },
        "nodes": nodes,
        "edges": edges,
    }


async def get_full_graph() -> dict[str, Any]:
    """Return all agents as nodes and all relationships as edges."""
    db = get_database()
    agent_repo = AgentRepository(db)
    rel_repo = RelationshipRepository(db)

    agents = await agent_repo.list_all()
    graph_data = await rel_repo.get_graph_data()

    nodes = [
        {
            "id": a["_id"],
            "name": a["name"],
            "status": a["status"],
            "agent_folders": a.get("agent_folders", []),
        }
        for a in agents
    ]

    return {"nodes": nodes, "edges": graph_data["edges"]}


async def get_agent_subgraph(agent_id: str) -> dict[str, Any]:
    db = get_database()
    rel_repo = RelationshipRepository(db)
    return await rel_repo.get_agent_subgraph(agent_id)
