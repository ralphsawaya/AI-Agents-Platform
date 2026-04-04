"""Agent lifecycle manager — registration, CRUD, source analysis."""

import ast
import io
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from agent_platform.config import settings
from agent_platform.core.validator import validate_agent_zip, validate_zip_security
from agent_platform.db.client import get_database
from agent_platform.db.repositories.agent_repo import AgentRepository
from agent_platform.db.repositories.relationship_repo import RelationshipRepository
from agent_platform.db.repositories.run_repo import RunRepository
from agent_platform.db.repositories.schedule_repo import ScheduleRepository

logger = logging.getLogger(__name__)


def _repos():
    db = get_database()
    return (
        AgentRepository(db),
        RunRepository(db),
        ScheduleRepository(db),
        RelationshipRepository(db),
    )


# ── Source analysis via Python AST ──


def _detect_nodes_and_tools(
    source_dir: Path,
    agent_folders: list[str] | None = None,
) -> tuple[list[str], list[str], dict[str, list[str]], dict[str, list[str]]]:
    """Walk all .py files and extract LangGraph node names and @tool functions.

    Returns flat lists for backward compatibility, plus per-agent-folder
    breakdowns so the UI can show which nodes/tools belong to which agent.
    """
    nodes: list[str] = []
    tools: list[str] = []
    nodes_by_agent: dict[str, list[str]] = {}
    tools_by_agent: dict[str, list[str]] = {}

    folder_set = set(agent_folders or [])

    for py_file in source_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        owning_folder: str | None = None
        if folder_set:
            rel_parts = py_file.relative_to(source_dir).parts
            if rel_parts and rel_parts[0] in folder_set:
                owning_folder = rel_parts[0]
            elif rel_parts and rel_parts[0] == "orchestrator":
                owning_folder = "orchestrator"

        file_nodes: list[str] = []
        file_tools: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "add_node"
                    and node.args
                ):
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(
                        first_arg.value, str
                    ):
                        file_nodes.append(first_arg.value)

            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    dec_name = None
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    if dec_name == "tool":
                        file_tools.append(node.name)

        nodes.extend(file_nodes)
        tools.extend(file_tools)

        if owning_folder and file_nodes:
            nodes_by_agent.setdefault(owning_folder, []).extend(file_nodes)
        if owning_folder and file_tools:
            tools_by_agent.setdefault(owning_folder, []).extend(file_tools)

    return nodes, tools, nodes_by_agent, tools_by_agent


_LLM_CLASS_NAMES = {
    "ChatOpenAI", "AzureChatOpenAI", "ChatAnthropic", "ChatGoogleGenerativeAI",
    "ChatCohere", "ChatMistralAI", "ChatOllama", "ChatGroq", "ChatBedrock",
    "ChatVertexAI", "ChatFireworks", "ChatTogether", "ChatPerplexity",
    "init_chat_model",
}

_LLM_MODULE_PREFIXES = (
    "langchain_openai", "langchain_anthropic", "langchain_google_genai",
    "langchain_cohere", "langchain_mistralai", "langchain_ollama",
    "langchain_groq", "langchain_aws", "langchain_google_vertexai",
    "langchain_fireworks", "langchain_together",
    "openai", "anthropic", "groq", "cohere", "mistralai",
    "google.genai", "google.generativeai",
)


def _detect_llm_usage(
    source_dir: Path,
    agent_folders: list[str] | None = None,
) -> dict[str, bool]:
    """Detect which agent folders instantiate or import LLM chat models.

    Handles both direct LLM SDK imports inside agent folders and indirect
    usage via shared modules (e.g. ``from shared.llm import get_llm``).

    Returns a dict mapping agent folder name → True for folders that use LLMs.
    """
    llm_by_agent: dict[str, bool] = {}
    folder_set = set(agent_folders or [])

    # Phase 1 — check if any non-agent module (e.g. shared/) provides LLM
    shared_llm_modules: set[str] = set()
    for py_file in source_dir.rglob("*.py"):
        rel_parts = py_file.relative_to(source_dir).parts
        if rel_parts and rel_parts[0] in folder_set:
            continue
        if "llm" in py_file.stem.lower():
            dotted = ".".join(rel_parts).removesuffix(".py")
            shared_llm_modules.add(dotted)

    # Phase 2 — scan agent folder files for LLM usage
    for py_file in source_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        owning_folder: str | None = None
        if folder_set:
            rel_parts = py_file.relative_to(source_dir).parts
            if rel_parts and rel_parts[0] in folder_set:
                owning_folder = rel_parts[0]

        if not owning_folder:
            continue

        if owning_folder in llm_by_agent:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Direct LLM SDK / LangChain imports
                if any(node.module.startswith(p) for p in _LLM_MODULE_PREFIXES):
                    llm_by_agent[owning_folder] = True
                    break
                # Import from a shared LLM module (e.g. shared.llm)
                if any(node.module == m or node.module.startswith(m + ".") for m in shared_llm_modules):
                    llm_by_agent[owning_folder] = True
                    break
                # Import with "llm" in the module path (e.g. from shared.llm import get_llm)
                if ".llm" in node.module or node.module.endswith(".llm"):
                    llm_by_agent[owning_folder] = True
                    break
                if node.names:
                    for alias in node.names:
                        if alias.name in _LLM_CLASS_NAMES:
                            llm_by_agent[owning_folder] = True
                            break
                    if owning_folder in llm_by_agent:
                        break
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(p) for p in _LLM_MODULE_PREFIXES):
                        llm_by_agent[owning_folder] = True
                        break
                if owning_folder in llm_by_agent:
                    break
            elif isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name and name in _LLM_CLASS_NAMES:
                    llm_by_agent[owning_folder] = True
                    break

    return llm_by_agent


def _detect_inter_agent_refs(
    source_dir: Path, agent_folders: list[str]
) -> list[dict[str, str]]:
    """Scan source files for cross-agent imports and references."""
    refs: list[dict[str, str]] = []
    folder_set = set(agent_folders)

    for py_file in source_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except SyntaxError:
            continue

        owning_agent = None
        rel_parts = py_file.relative_to(source_dir).parts
        if rel_parts and rel_parts[0] in folder_set:
            owning_agent = rel_parts[0]
        elif rel_parts and rel_parts[0] == "orchestrator":
            owning_agent = "orchestrator"

        for node in ast.walk(tree):
            # import agent_alpha.something or from agent_beta import ...
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = None
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        _check_ref(module, owning_agent, folder_set, refs, "imports")
                    continue
                if module:
                    _check_ref(module, owning_agent, folder_set, refs, "imports")

        # Regex fallback for string-based references like "agent_alpha"
        for other in folder_set:
            if owning_agent and other != owning_agent:
                if re.search(rf"\b{re.escape(other)}\b", content):
                    ref = {"source": owning_agent or "unknown", "target": other, "type": "calls"}
                    if ref not in refs:
                        refs.append(ref)

    return refs


def _check_ref(
    module: str | None,
    owning: str | None,
    folder_set: set[str],
    refs: list[dict[str, str]],
    rel_type: str,
) -> None:
    if module is None:
        return
    top = module.split(".")[0]
    if top in folder_set and top != owning:
        ref = {"source": owning or "unknown", "target": top, "type": rel_type}
        if ref not in refs:
            refs.append(ref)


_SKIP_DIRS = {".venv", "__pycache__", "logs", ".git", "node_modules", ".mypy_cache", ".ruff_cache"}
_SKIP_FILES = {".DS_Store", ".gitkeep", ".gitignore", ".env"}
_SKIP_SUFFIXES = {".pyc", ".pyo", ".pyd", ".zip"}


def _build_source_structure(base: Path) -> dict[str, Any]:
    """Build a nested dict representing the file tree for the UI file browser.

    Excludes virtual environments, caches, compiled files, and other noise
    so only meaningful source files are shown.
    """
    structure: dict[str, Any] = {}
    for item in sorted(base.rglob("*")):
        rel = item.relative_to(base)
        parts = rel.parts
        # Skip anything inside a noise directory
        if any(p in _SKIP_DIRS for p in parts):
            continue
        # Skip noise files and compiled artifacts
        if item.is_file() and (item.name in _SKIP_FILES or item.suffix in _SKIP_SUFFIXES):
            continue
        node = structure
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        if item.is_file():
            node[parts[-1]] = None  # leaf
        else:
            node.setdefault(parts[-1], {})
    return structure


def _parse_agent_configs(base: Path, agent_folders: list[str]) -> dict[str, Any]:
    """Read config.yaml from each agent folder."""
    configs: dict[str, Any] = {}
    for folder in agent_folders:
        cfg_path = base / folder / "config.yaml"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r") as f:
                    configs[folder] = yaml.safe_load(f) or {}
            except Exception:
                configs[folder] = {}
    return configs


def _read_readme(base: Path) -> str | None:
    """Read a README.md file from the agent root if it exists."""
    for name in ("README.md", "readme.md", "Readme.md"):
        path = base / name
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Failed to read %s in %s", name, base)
    return None


def _parse_run_config(base: Path) -> dict[str, Any] | None:
    """Read run_config.json from the agent root if it exists.

    This allows each agent team to define a custom input form for the Run modal
    instead of the default raw-JSON textarea.
    """
    import json

    cfg_path = base / "run_config.json"
    if not cfg_path.exists():
        return None
    try:
        with open(cfg_path, "r") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to parse run_config.json in %s", base)
        return None


def _parse_custom_tabs(base: Path) -> list[dict[str, str]] | None:
    """Read ui/tabs.json from the agent root if it exists.

    This allows each agent team to ship custom UI tabs that the platform
    loads as plugin fragments on the agent detail page.  Each tab references
    an HTML file under ui/tabs/<id>.html.
    """
    import json

    cfg_path = base / "ui" / "tabs.json"
    if not cfg_path.exists():
        return None
    try:
        with open(cfg_path, "r") as f:
            data = json.load(f)
        tabs = data.get("tabs", [])
        if not tabs:
            return None
        valid = []
        for t in tabs:
            tab_id = t.get("id")
            label = t.get("label")
            if not tab_id or not label:
                continue
            html_path = base / "ui" / "tabs" / f"{tab_id}.html"
            if html_path.exists():
                valid.append({"id": tab_id, "label": label})
            else:
                logger.warning("Custom tab '%s' declared but %s not found", tab_id, html_path)
        return valid if valid else None
    except Exception:
        logger.warning("Failed to parse ui/tabs.json in %s", base)
        return None


def _strip_env_secrets(env_path: Path) -> None:
    """Preserved for backward compatibility — team .env files are now kept
    intact so each agent team can manage its own credentials."""
    return


# ── Public API ──


async def register_agent(
    file_bytes: bytes,
    filename: str,
    name: str | None = None,
    description: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Validate, extract, analyse, and register an uploaded agent zip."""
    validation = validate_agent_zip(file_bytes)
    if not validation.valid:
        raise ValueError("; ".join(validation.errors))

    agent_id = str(uuid4())
    store = Path(settings.AGENTS_STORE_PATH) / agent_id
    store.mkdir(parents=True, exist_ok=True)

    zf = zipfile.ZipFile(io.BytesIO(file_bytes))

    # Zip-slip protection before extraction
    offenders = validate_zip_security(zf, str(store))
    if offenders:
        shutil.rmtree(store, ignore_errors=True)
        raise ValueError(
            f"Zip contains path-traversal entries (zip-slip): {offenders[:5]}"
        )

    zf.extractall(store)

    # The extracted content lives under store/<root_folder>/
    root_dir = store / validation.root_folder

    _strip_env_secrets(root_dir / ".env")

    source_structure = _build_source_structure(root_dir)
    detected_nodes, detected_tools, nodes_by_agent, tools_by_agent = (
        _detect_nodes_and_tools(root_dir, validation.agent_folders)
    )
    llm_by_agent = _detect_llm_usage(root_dir, validation.agent_folders)
    agent_configs = _parse_agent_configs(root_dir, validation.agent_folders)
    run_config = _parse_run_config(root_dir)
    custom_tabs = _parse_custom_tabs(root_dir)
    readme_md = _read_readme(root_dir)

    agent_repo, *_ = _repos()

    agent_name = name or validation.root_folder
    agent_doc: dict[str, Any] = {
        "_id": agent_id,
        "name": agent_name,
        "description": description,
        "tags": tags or [],
        "root_folder": validation.root_folder,
        "entry_point": "orchestrator/main.py",
        "agent_folders": validation.agent_folders,
        "has_orchestrator": True,
        "upload_path": str(store),
        "venv_path": str(store / ".venv"),
        "source_structure": source_structure,
        "detected_nodes": detected_nodes,
        "detected_tools": detected_tools,
        "nodes_by_agent": nodes_by_agent,
        "tools_by_agent": tools_by_agent,
        "llm_by_agent": llm_by_agent,
    }
    if run_config:
        agent_doc["run_config"] = run_config
    if custom_tabs:
        agent_doc["custom_tabs"] = custom_tabs
    if readme_md:
        agent_doc["description"] = readme_md
    doc = await agent_repo.create(agent_doc)

    # Store agent configs as part of the document
    if agent_configs:
        await agent_repo.update(agent_id, {"agent_configs": agent_configs})

    # Tag management
    rel_repo = RelationshipRepository(get_database())
    for tag in tags or []:
        await rel_repo.upsert_tag(tag, agent_id)

    # Static analysis for inter-agent relationships
    refs = _detect_inter_agent_refs(root_dir, validation.agent_folders)
    if refs:
        # These are intra-package references. We store them with the agent's own id
        # as both source and target since they belong to the same upload.
        await agent_repo.update(agent_id, {"internal_refs": refs})

    logger.info("Agent %s registered (id=%s, agents=%s)", agent_name, agent_id, validation.agent_folders)
    return doc


async def get_agent(agent_id: str) -> dict[str, Any] | None:
    agent_repo = AgentRepository(get_database())
    agent = await agent_repo.get_by_id(agent_id)
    if agent:
        root_dir = Path(agent.get("upload_path", "")) / agent.get("root_folder", "")
        run_config = _parse_run_config(root_dir)
        if run_config:
            agent["run_config"] = run_config
            if agent.get("_run_config_hash") != str(run_config):
                await agent_repo.update(agent_id, {"run_config": run_config, "_run_config_hash": str(run_config)})
    return agent


async def list_agents(
    status: str | None = None,
    tags: list[str] | None = None,
    name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    agent_repo = AgentRepository(get_database())
    return await agent_repo.list_all(status=status, tags=tags, name=name, date_from=date_from, date_to=date_to)


async def delete_agent(agent_id: str) -> bool:
    agent_repo, run_repo, schedule_repo, rel_repo = _repos()
    db = get_database()

    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        return False

    # Remove disk files
    upload_path = agent.get("upload_path", "")
    if upload_path and os.path.isdir(upload_path):
        shutil.rmtree(upload_path, ignore_errors=True)

    # Cascade-delete related documents
    await schedule_repo.delete_by_agent(agent_id)
    await rel_repo.delete_by_agent(agent_id)
    await rel_repo.remove_agent_from_tags(agent_id)

    # Clean up team settings (LLM config + integration keys)
    await db["team_settings"].delete_one({"_id": agent_id})

    # Clean up run history
    await db["agent_runs"].delete_many({"agent_id": agent_id})

    await agent_repo.delete(agent_id)

    logger.info("Agent %s deleted (all related data cleaned up)", agent_id)
    return True


def get_file_tree(agent_id: str) -> dict[str, Any] | None:
    """Return a serialisable file tree dict for an agent's extracted folder."""
    base = Path(settings.AGENTS_STORE_PATH) / agent_id
    if not base.exists():
        return None
    return _build_source_structure(base)


def get_file_content(agent_id: str, rel_path: str) -> str | None:
    """Read a source file from the agent's extracted folder.

    Returns None if the file doesn't exist or the path escapes the agent dir.
    """
    base = Path(settings.AGENTS_STORE_PATH) / agent_id
    target = (base / rel_path).resolve()
    # Guard against path traversal
    if not str(target).startswith(str(base.resolve())):
        return None
    if not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
