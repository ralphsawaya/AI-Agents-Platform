"""ZIP structure validation engine for uploaded agent packages.

Enforces the required folder/file hierarchy and guards against
zip-slip (path traversal) attacks.
"""

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    root_folder: str = ""
    agent_folders: list[str] = field(default_factory=list)
    all_paths: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.valid = False
        self.errors.append(msg)


SHARED_REQUIRED_FILES = [
    "__init__.py",
    "models.py",
    "config.py",
    "logger.py",
    "utils.py",
    "llm.py",
]

AGENT_REQUIRED_FILES = [
    "main.py",
    "agent.py",
    "state.py",
    "config.yaml",
    "requirements.txt",
]

AGENT_REQUIRED_SUBDIRS = [
    "nodes",
    "edges",
    "tools",
    "memory",
    "prompts",
]

ORCHESTRATOR_REQUIRED_FILES = [
    "main.py",
    "graph.py",
    "state.py",
]


def _has_path(paths: set[str], root: str, *parts: str) -> bool:
    """Check whether a file or directory exists in the zip's path set."""
    target = "/".join([root, *parts])
    if target in paths:
        return True
    # directories may appear with or without trailing slash, or only
    # implicitly via their children
    dir_prefix = target.rstrip("/") + "/"
    return any(p.startswith(dir_prefix) for p in paths)


def validate_zip_security(zf: zipfile.ZipFile, target_dir: str) -> list[str]:
    """Guard against zip-slip: every extracted path must resolve under target_dir.

    Returns a list of offending entry names (empty means safe).
    """
    from pathlib import Path

    target = Path(target_dir).resolve()
    offenders: list[str] = []
    for entry in zf.namelist():
        resolved = (target / entry).resolve()
        if not str(resolved).startswith(str(target)):
            offenders.append(entry)
    return offenders


def validate_agent_zip(file_bytes: bytes) -> ValidationResult:
    """Run full structural validation on an in-memory zip file.

    Returns a ValidationResult with detailed errors if any rule fails.
    """
    result = ValidationResult()

    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        result.add_error("Uploaded file is not a valid ZIP archive.")
        return result

    names = zf.namelist()
    result.all_paths = names

    if not names:
        result.add_error("ZIP archive is empty.")
        return result

    # ── 1. Exactly one root folder ──
    top_level = {PurePosixPath(n).parts[0] for n in names if n != "/"}
    if len(top_level) != 1:
        result.add_error(
            f"ZIP must contain exactly one root folder. Found: {sorted(top_level)}"
        )
        return result

    root = top_level.pop()
    result.root_folder = root
    path_set = set(names)

    # ── 2. shared/ folder and its required files ──
    if not _has_path(path_set, root, "shared"):
        result.add_error(f"Missing required folder: {root}/shared/")
    else:
        for fname in SHARED_REQUIRED_FILES:
            if not _has_path(path_set, root, "shared", fname):
                result.add_error(f"Missing required file: {root}/shared/{fname}")

    # ── 3. At least one agent_*/ folder ──
    all_second_level = set()
    for n in names:
        parts = PurePosixPath(n).parts
        if len(parts) >= 2 and parts[0] == root:
            all_second_level.add(parts[1])

    agent_dirs = sorted(d for d in all_second_level if d.startswith("agent_"))
    if not agent_dirs:
        result.add_error(
            "At least one agent folder (agent_*/) is required inside the root."
        )
    else:
        result.agent_folders = agent_dirs
        for adir in agent_dirs:
            for fname in AGENT_REQUIRED_FILES:
                if not _has_path(path_set, root, adir, fname):
                    result.add_error(f"Missing required file: {root}/{adir}/{fname}")
            for subdir in AGENT_REQUIRED_SUBDIRS:
                if not _has_path(path_set, root, adir, subdir):
                    result.add_error(
                        f"Missing required subdirectory: {root}/{adir}/{subdir}/"
                    )

    # ── 4. orchestrator/ with required files ──
    if not _has_path(path_set, root, "orchestrator"):
        result.add_error(f"Missing required folder: {root}/orchestrator/")
    else:
        for fname in ORCHESTRATOR_REQUIRED_FILES:
            if not _has_path(path_set, root, "orchestrator", fname):
                result.add_error(
                    f"Missing required file: {root}/orchestrator/{fname}"
                )

    # ── 5. Other required top-level directories ──
    for dname in ("tests", "data", "checkpoints"):
        if not _has_path(path_set, root, dname):
            result.add_error(f"Missing required folder: {root}/{dname}/")

    if not _has_path(path_set, root, "data", "inputs"):
        result.add_error(f"Missing required folder: {root}/data/inputs/")
    if not _has_path(path_set, root, "data", "outputs"):
        result.add_error(f"Missing required folder: {root}/data/outputs/")

    # ── 6. Top-level requirements.txt ──
    if not _has_path(path_set, root, "requirements.txt"):
        result.add_error(f"Missing required file: {root}/requirements.txt")

    return result
