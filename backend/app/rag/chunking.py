"""
Smart chunking: split code around function/class boundaries instead of
naive fixed-size windows, so a chunk doesn't cut a function in half. Falls
back to a token-based recursive splitter for languages/files where we don't
have a boundary regex (or the boundary produces an oversized block).
"""
import re
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

# Rough per-language patterns for top-level function/class definitions.
# Not a full parser -- good enough to find natural chunk boundaries quickly
# without pulling in a heavyweight AST toolchain per language.
BOUNDARY_PATTERNS: dict[str, re.Pattern] = {
    "Python": re.compile(r"^(class |def |async def )", re.MULTILINE),
    "JavaScript": re.compile(
        r"^(export\s+)?(async\s+)?function\s+\w+|^class\s+\w+|^(export\s+)?const\s+\w+\s*=\s*(async\s*)?\(", re.MULTILINE
    ),
    "TypeScript": re.compile(
        r"^(export\s+)?(async\s+)?function\s+\w+|^(export\s+)?class\s+\w+|^(export\s+)?interface\s+\w+", re.MULTILINE
    ),
    "Java": re.compile(r"^\s*(public|private|protected|static).*?(class|interface|\w+\s*\()", re.MULTILINE),
    "Go": re.compile(r"^func\s+", re.MULTILINE),
}

_fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.CHUNK_SIZE_TOKENS * 4,  # rough chars-per-token heuristic
    chunk_overlap=settings.CHUNK_OVERLAP_TOKENS * 4,
    separators=["\n\n", "\n", " ", ""],
)


@dataclass
class CodeChunk:
    content: str
    start_line: int
    end_line: int
    function_name: str | None = None
    class_name: str | None = None
    metadata: dict = field(default_factory=dict)


def _extract_symbol_name(line: str) -> tuple[str | None, str | None]:
    """Best-effort extraction of function_name/class_name from a boundary line."""
    class_match = re.search(r"class\s+(\w+)", line)
    func_match = re.search(r"(?:def|function)\s+(\w+)", line)
    return (
        func_match.group(1) if func_match else None,
        class_match.group(1) if class_match else None,
    )


def chunk_file(content: str, language: str | None) -> list[CodeChunk]:
    pattern = BOUNDARY_PATTERNS.get(language or "")
    if pattern is None:
        return _fallback_chunk(content)

    lines = content.splitlines()
    boundary_line_indices = [i for i, line in enumerate(lines) if pattern.match(line)]

    if not boundary_line_indices:
        return _fallback_chunk(content)

    chunks: list[CodeChunk] = []
    # Leading content before the first boundary (imports, module docstring, etc.)
    if boundary_line_indices[0] > 0:
        header = "\n".join(lines[: boundary_line_indices[0]]).strip()
        if header:
            chunks.append(CodeChunk(content=header, start_line=1, end_line=boundary_line_indices[0]))

    for idx, start in enumerate(boundary_line_indices):
        end = boundary_line_indices[idx + 1] if idx + 1 < len(boundary_line_indices) else len(lines)
        block = "\n".join(lines[start:end])

        # Oversized block (e.g. a huge class) - recursively split further.
        if len(block) > settings.CHUNK_SIZE_TOKENS * 4 * 1.5:
            for sub in _fallback_splitter.split_text(block):
                func_name, class_name = _extract_symbol_name(lines[start])
                chunks.append(
                    CodeChunk(content=sub, start_line=start + 1, end_line=end,
                               function_name=func_name, class_name=class_name)
                )
            continue

        func_name, class_name = _extract_symbol_name(lines[start])
        chunks.append(
            CodeChunk(content=block, start_line=start + 1, end_line=end,
                      function_name=func_name, class_name=class_name)
        )

    return chunks


def _fallback_chunk(content: str) -> list[CodeChunk]:
    texts = _fallback_splitter.split_text(content)
    chunks = []
    cursor = 1
    for text in texts:
        line_count = text.count("\n") + 1
        chunks.append(CodeChunk(content=text, start_line=cursor, end_line=cursor + line_count - 1))
        cursor += line_count
    return chunks
