from __future__ import annotations

import hashlib
import re
from typing import TypedDict

from app.reviewer import AddedLine, ReviewReport, added_lines, review_patch

try:
    from tree_sitter_language_pack import get_parser
except ImportError:
    get_parser = None

try:
    from qdrant_client import QdrantClient, models
except ImportError:
    QdrantClient = None
    models = None

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:
    END = START = StateGraph = None


class ReviewState(TypedDict, total=False):
    patch: str
    sources: dict[str, str]
    changed_lines: list[AddedLine]
    related_context: list[str]
    report: ReviewReport


_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}
_SYMBOL_TYPES = {
    "function_definition", "class_definition", "function_declaration",
    "method_definition", "class_declaration", "function_item",
}


def _function_context(path: str, source: str) -> list[str]:
    if get_parser is None:
        return []
    extension = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    language = _LANGUAGES.get(extension)
    if not language:
        return []
    try:
        tree = get_parser(language).parse(source.encode("utf-8"))
    except (LookupError, ValueError):
        return []

    source_lines = source.splitlines()
    snippets: list[str] = []
    nodes = [tree.root_node]
    while nodes:
        node = nodes.pop()
        if node.type in _SYMBOL_TYPES:
            start = node.start_point.row
            end = min(node.end_point.row + 1, start + 80, len(source_lines))
            snippets.append(f"{path}:{start + 1}\n" + "\n".join(source_lines[start:end]))
        nodes.extend(reversed(node.children))
    return snippets


def _vector(text: str) -> list[float]:
    vector = [0.0] * 96
    for token in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", text.lower()):
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "little") % len(vector)
        vector[slot] += 1.0 if digest[4] & 1 else -1.0
    return vector


def _retrieve_context(lines: list[AddedLine], sources: dict[str, str]) -> list[str]:
    symbols = [symbol for path, source in sources.items() for symbol in _function_context(path, source)]
    if not symbols:
        return []

    if QdrantClient is not None and models is not None:
        try:
            client = QdrantClient(":memory:")
            collection = "review_context"
            client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(size=96, distance=models.Distance.COSINE),
            )
            client.upsert(
                collection_name=collection,
                points=[
                    models.PointStruct(id=index, vector=_vector(symbol), payload={"text": symbol})
                    for index, symbol in enumerate(symbols)
                ],
            )
            related: dict[str, None] = {}
            for line in lines[:30]:
                result = client.query_points(
                    collection_name=collection,
                    query=_vector(line.text),
                    limit=2,
                )
                for point in result.points:
                    related[str(point.payload["text"])] = None
                    if len(related) >= 8:
                        break
            client.close()
            return list(related)
        except Exception:
            pass

    return symbols[:8]


def _retrieve_node(state: ReviewState) -> ReviewState:
    lines = list(added_lines(state["patch"]))
    return {
        "changed_lines": lines,
        "related_context": _retrieve_context(lines, state.get("sources", {})),
    }


def _audit_node(state: ReviewState) -> ReviewState:
    return {"report": review_patch(state["patch"])}


def _synthesize_node(state: ReviewState) -> ReviewState:
    report = ReviewReport.model_validate(state["report"].model_dump())
    return {"report": report}


def review_pull_request(patch: str, sources: dict[str, str] | None = None) -> ReviewReport:
    state: ReviewState = {"patch": patch, "sources": sources or {}}
    if StateGraph is None:
        retrieved = _retrieve_node(state)
        audited = _audit_node({**state, **retrieved})
        return _synthesize_node({**state, **retrieved, **audited})["report"]

    graph = StateGraph(ReviewState)
    graph.add_node("context_retriever", _retrieve_node)
    graph.add_node("security_bug_auditor", _audit_node)
    graph.add_node("pydantic_synthesizer", _synthesize_node)
    graph.add_edge(START, "context_retriever")
    graph.add_edge("context_retriever", "security_bug_auditor")
    graph.add_edge("security_bug_auditor", "pydantic_synthesizer")
    graph.add_edge("pydantic_synthesizer", END)
    return graph.compile().invoke(state)["report"]