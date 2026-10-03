import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import git

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.language_detect import detect_primary_language, is_ignored_path

logger = get_logger(__name__)

GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(\.git)?/?$"
)

# Only index source-ish, human-readable files; skip binaries/lockfiles/assets.
ALLOWED_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".kt", ".swift", ".scala", ".sql",
    ".sh", ".yaml", ".yml", ".md", ".json", ".toml",
}
MAX_FILE_SIZE_BYTES = 500_000  # skip generated/huge files


@dataclass
class RepoFile:
    path: str  # path relative to repo root
    content: str
    language: str | None


@dataclass
class ParsedRepository:
    local_path: Path
    commit_sha: str
    primary_language: str | None
    files: list[RepoFile]


def validate_github_url(url: str) -> tuple[str, str]:
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise ValueError(f"Not a valid GitHub repository URL: {url}")
    return match.group("owner"), match.group("repo")


def clone_repository(github_url: str, branch: str, repo_id: str) -> Path:
    owner, repo = validate_github_url(github_url)
    dest = Path(settings.GITHUB_CLONE_DIR) / repo_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    clone_url = github_url
    if settings.GITHUB_TOKEN:
        # Inject token for private repos; never logged.
        clone_url = github_url.replace(
            "https://github.com", f"https://{settings.GITHUB_TOKEN}@github.com"
        )

    logger.info("cloning_repository", owner=owner, repo=repo, branch=branch)
    git.Repo.clone_from(clone_url, dest, branch=branch, depth=1, single_branch=True)
    return dest


def parse_repository(local_path: Path) -> ParsedRepository:
    repo = git.Repo(local_path)
    commit_sha = repo.head.commit.hexsha

    files: list[RepoFile] = []
    all_paths: list[Path] = []

    for path in local_path.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(local_path)
        if is_ignored_path(rel_path):
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        all_paths.append(rel_path)
        files.append(RepoFile(path=str(rel_path), content=content, language=None))

    primary_language = detect_primary_language(all_paths)

    return ParsedRepository(
        local_path=local_path,
        commit_sha=commit_sha,
        primary_language=primary_language,
        files=files,
    )
