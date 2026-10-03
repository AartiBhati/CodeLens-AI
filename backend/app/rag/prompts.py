from langchain_core.prompts import ChatPromptTemplate

NO_EVIDENCE_MESSAGE = "I couldn't find evidence in this repository."

_BASE_SYSTEM = f"""You are CodeLens AI, an expert assistant that answers questions strictly \
using the provided repository context. Rules:

1. Only use the CONTEXT below. Never invent code, files, or behavior that isn't shown.
2. If the context does not contain enough evidence to answer, reply exactly: \
"{NO_EVIDENCE_MESSAGE}"
3. When you reference code, cite the file path (and function/class name if given).
4. Be precise and concise. Prefer short code excerpts over long ones.
5. If asked a follow-up, use the conversation history to resolve pronouns/references, \
but still ground the technical answer in CONTEXT."""

ASK_CODEBASE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _BASE_SYSTEM),
        ("system", "CONVERSATION SUMMARY (older turns): {summary}"),
        ("placeholder", "{history}"),
        ("system", "CONTEXT:\n{context}"),
        ("human", "{question}"),
    ]
)

EXPLAIN_FILE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _BASE_SYSTEM),
        (
            "human",
            "Explain what the file `{file_path}` does: its purpose, key functions/classes, "
            "and how it likely interacts with the rest of the codebase.\n\nCONTEXT:\n{context}",
        ),
    ]
)

GENERATE_DOCS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _BASE_SYSTEM),
        (
            "human",
            "Generate clear markdown documentation for `{file_path}`, including a summary, "
            "a function/class reference table, and usage notes if inferable.\n\nCONTEXT:\n{context}",
        ),
    ]
)

ARCHITECTURE_ANALYZER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _BASE_SYSTEM),
        (
            "human",
            "Based on the retrieved code, explain how these modules interact "
            "(data flow, dependencies, layering). Question: {question}\n\nCONTEXT:\n{context}",
        ),
    ]
)

BUG_INVESTIGATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _BASE_SYSTEM),
        (
            "human",
            "A developer reported this error/symptom: {question}\n\n"
            "Using the retrieved code, identify the most likely cause and where to look. "
            "Do not claim certainty the context doesn't support.\n\nCONTEXT:\n{context}",
        ),
    ]
)

RELATED_FILES_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _BASE_SYSTEM),
        (
            "human",
            "List the files most semantically related to: {question}. Explain briefly why each "
            "is related.\n\nCONTEXT:\n{context}",
        ),
    ]
)

SUMMARIZE_HISTORY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Summarize the following conversation between a developer and CodeLens AI into a "
            "concise paragraph preserving all technical facts, file names, and decisions made. "
            "This summary will replace the raw messages to keep the prompt short.",
        ),
        ("human", "{conversation_text}"),
    ]
)

PROMPT_REGISTRY = {
    "ask_codebase": ASK_CODEBASE_PROMPT,
    "explain_file": EXPLAIN_FILE_PROMPT,
    "generate_docs": GENERATE_DOCS_PROMPT,
    "architecture_analyzer": ARCHITECTURE_ANALYZER_PROMPT,
    "bug_investigation": BUG_INVESTIGATION_PROMPT,
    "related_files": RELATED_FILES_PROMPT,
}
