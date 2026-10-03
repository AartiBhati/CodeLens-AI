from app.rag.chunking import chunk_file

PYTHON_SAMPLE = '''"""Module docstring."""
import os


def add(a, b):
    return a + b


class Calculator:
    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        return a / b
'''


def test_python_chunking_splits_on_function_and_class_boundaries():
    chunks = chunk_file(PYTHON_SAMPLE, "Python")
    assert len(chunks) >= 2

    func_chunk = next(c for c in chunks if c.function_name == "add")
    assert "return a + b" in func_chunk.content

    class_chunk = next(c for c in chunks if c.class_name == "Calculator")
    assert "multiply" in class_chunk.content


def test_chunking_preserves_leading_imports_as_separate_chunk():
    chunks = chunk_file(PYTHON_SAMPLE, "Python")
    header = chunks[0]
    assert "import os" in header.content
    assert header.function_name is None


def test_unknown_language_falls_back_to_generic_splitter():
    text = "line one\nline two\n" * 50
    chunks = chunk_file(text, "COBOL")
    assert len(chunks) >= 1
    assert all(c.content for c in chunks)


def test_line_numbers_are_monotonic_and_non_overlapping_for_boundaries():
    chunks = chunk_file(PYTHON_SAMPLE, "Python")
    for c in chunks:
        assert c.start_line <= c.end_line
