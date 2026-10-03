"""
LangChain tools available to the CodeLens agent. Every tool takes a
`repository_id` that the caller controls (never trusted from the LLM output
directly for the *initial* scoping) -- see `make_repository_tools`, which
binds repository_id via closure so the model literally cannot query a
different, unauthorized repository even if it tried.
"""
import subprocess
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.config import settings
from app.rag.retriever import retrieve


class SearchCodeInput(BaseModel):
    query: str = Field(description="Natural language or symbol name to search for in the codebase")


class GetFileInput(BaseModel):
    file_path: str = Field(description="Repository-relative file path to read")


class SearchCommitHistoryInput(BaseModel):
    query: str = Field(description="Keyword to search for in commit messages")
    max_results: int = Field(default=10, le=50)


def make_repository_tools(repository_id: str, local_repo_path: Path | None) -> list[StructuredTool]:
    """Factory that closes over repository_id/local_repo_path so tool calls
    are always authorization-scoped to the repository the user is asking about."""

    def search_code(query: str) -> str:
        results = retrieve(question=query, repository_id=repository_id, top_k=5)
        if not results:
            return "No matching code found."
        return "\n\n---\n\n".join(
            f"{r['file_path']} (lines {r['start_line']}-{r['end_line']}):\n{r['text']}" for r in results
        )

    def get_file(file_path: str) -> str:
        if local_repo_path is None:
            return "File contents are unavailable: repository is not checked out locally."
        # Prevent path traversal outside the cloned repo.
        target = (local_repo_path / file_path).resolve()
        if local_repo_path.resolve() not in target.parents and target != local_repo_path.resolve():
            return "Access denied: path escapes repository root."
        if not target.exists() or not target.is_file():
            return f"File not found: {file_path}"
        return target.read_text(encoding="utf-8", errors="ignore")[:20_000]

    def repository_tree() -> str:
        if local_repo_path is None:
            return "Repository tree is unavailable: not checked out locally."
        lines = []
        for path in sorted(local_repo_path.rglob("*")):
            if path.is_file() and ".git" not in path.parts:
                lines.append(str(path.relative_to(local_repo_path)))
        return "\n".join(lines[:2000])

    def search_commit_history(query: str, max_results: int = 10) -> str:
        if local_repo_path is None:
            return "Commit history is unavailable: repository is not checked out locally."
        try:
            output = subprocess.run(
                ["git", "log", f"--grep={query}", f"-n{max_results}", "--oneline"],
                cwd=local_repo_path,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return output.stdout.strip() or "No matching commits found."
        except (subprocess.SubprocessError, OSError) as exc:
            return f"Could not search commit history: {exc}"

    return [
        StructuredTool.from_function(
            func=search_code,
            name="search_code",
            description="Semantically search the indexed codebase for relevant code chunks.",
            args_schema=SearchCodeInput,
        ),
        StructuredTool.from_function(
            func=get_file,
            name="get_file",
            description="Read the full contents of a specific file in the repository.",
            args_schema=GetFileInput,
        ),
        StructuredTool.from_function(
            func=repository_tree,
            name="repository_tree",
            description="List every indexed file path in the repository.",
        ),
        StructuredTool.from_function(
            func=search_commit_history,
            name="search_commit_history",
            description="Search commit messages in the repository's git history.",
            args_schema=SearchCommitHistoryInput,
        ),
    ]
