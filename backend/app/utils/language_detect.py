from collections import Counter
from pathlib import Path

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
}

IGNORED_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".pytest_cache", "target", "vendor", ".idea", ".vscode", "coverage",
}


def is_ignored_path(path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in path.parts)


def detect_primary_language(file_paths: list[Path]) -> str | None:
    counts: Counter[str] = Counter()
    for path in file_paths:
        lang = EXTENSION_LANGUAGE_MAP.get(path.suffix.lower())
        if lang:
            counts[lang] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]
