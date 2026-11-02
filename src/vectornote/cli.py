"""Command-line interface for VectorNote."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path

from vectornote import __version__
from vectornote.config import Settings
from vectornote.embeddings.encoder import EmbedderUnavailableError
from vectornote.evaluation.dataset import (
    DatasetError,
    check_questions,
    load_questions,
    write_questions,
)
from vectornote.evaluation.metrics import AnswerRecord, AnswerSummary
from vectornote.evaluation.report import (
    RunInfo,
    build_payload,
    format_markdown,
    format_text,
    write_json,
)
from vectornote.evaluation.runner import resolve_queries, run_answers, run_retrieval
from vectornote.evaluation.scaffold import draft_questions, sample_chunks
from vectornote.generation import OllamaError
from vectornote.ingestion.chunking import chunk_document
from vectornote.ingestion.cleaning import clean_document
from vectornote.ingestion.loaders import (
    DocumentLoadError,
    UnsupportedFileTypeError,
    load_document,
)
from vectornote.models import AskResult, ChatTurn, Document, SearchResult
from vectornote.retrieval import MODES
from vectornote.service import IngestResult, QueryEvent, RagService, TokenEvent
from vectornote.store import EmbeddingModelMismatchError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vectornote",
        description="Offline RAG study assistant.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    ingest = sub.add_parser("ingest", help="Index documents (default: the data directory).")
    ingest.add_argument("paths", nargs="*", type=Path, help="files or folders to ingest")
    ingest.add_argument("--force", action="store_true", help="re-index unchanged files too")
    ingest.add_argument(
        "--prune", action="store_true", help="drop indexed files that left the data directory"
    )
    evaluate = sub.add_parser("eval", help="Build, check and run the evaluation question set.")
    eval_sub = evaluate.add_subparsers(dest="eval_command", required=True)
    scaffold = eval_sub.add_parser(
        "scaffold", help="Draft a question file that points at real pages of your documents."
    )
    scaffold.add_argument("-n", "--count", type=int, default=40, help="number of drafts")
    scaffold.add_argument("--seed", type=int, default=42, help="same seed, same pages")
    scaffold.add_argument("-o", "--output", type=Path, default=Path("eval/draft.jsonl"))
    scaffold.add_argument(
        "--suggest",
        action="store_true",
        help="let the model propose a question and answer for each page (you must review them)",
    )
    scaffold.add_argument("--force", action="store_true", help="overwrite the output file")
    check = eval_sub.add_parser("check", help="Validate a question file against the index.")
    check.add_argument("path", type=Path, nargs="?", default=Path("eval/questions.jsonl"))
    run = eval_sub.add_parser(
        "run", help="Measure retrieval (hit rate, MRR, latency) and answer quality."
    )
    run.add_argument("path", type=Path, nargs="?", default=Path("eval/questions.jsonl"))
    run.add_argument("-k", "--top-k", type=int, default=5, help="passages per question")
    run.add_argument(
        "--mode",
        action="append",
        choices=MODES,
        dest="modes",
        help="search mode to measure (repeatable; default: all three)",
    )
    run.add_argument(
        "--rewrite",
        action="store_true",
        help="include follow-up questions in the retrieval benchmark (needs Ollama)",
    )
    run.add_argument(
        "--answers", action="store_true", help="also measure the answers (needs Ollama)"
    )
    run.add_argument(
        "--answer-mode",
        choices=MODES,
        default=None,
        help="search mode used for the answers (default: VECTORNOTE_RETRIEVAL_MODE)",
    )
    run.add_argument(
        "--judge",
        action="store_true",
        help="let the model judge whether each answer is faithful to its passages (--answers)",
    )
    run.add_argument(
        "--format", choices=("text", "markdown"), default="text", help="how to print the results"
    )
    run.add_argument(
        "-o", "--output", type=Path, default=None, help="save all results and answers as JSON"
    )
    chat = sub.add_parser("chat", help="Talk to your documents; follow-up questions work.")
    chat.add_argument("-k", "--top-k", type=int, default=None, help="passages per question")
    chat.add_argument(
        "--source", action="append", dest="sources", help="only use this file (repeatable)"
    )
    chat.add_argument("--mode", choices=MODES, default=None, help="vector, bm25 or hybrid")
    ask = sub.add_parser("ask", help="Ask a question and get a cited answer.")
    ask.add_argument("question")
    ask.add_argument("-k", "--top-k", type=int, default=None, help="passages given to the model")
    ask.add_argument(
        "--source", action="append", dest="sources", help="only use this file (repeatable)"
    )
    ask.add_argument("--mode", choices=MODES, default=None, help="vector, bm25 or hybrid")
    ask.add_argument(
        "--no-stream", action="store_true", help="wait for the whole answer instead of streaming"
    )
    search = sub.add_parser("search", help="Find the most relevant passages for a question.")
    search.add_argument("query")
    search.add_argument("-k", "--top-k", type=int, default=None, help="number of results")
    search.add_argument(
        "--source", action="append", dest="sources", help="only search this file (repeatable)"
    )
    search.add_argument(
        "--mode",
        choices=MODES,
        default=None,
        help="vector, bm25 or hybrid (default: VECTORNOTE_RETRIEVAL_MODE, else hybrid)",
    )
    search.add_argument(
        "--min-score", type=float, default=None, help="drop matches below this cosine similarity"
    )
    search.add_argument("--full", action="store_true", help="print the whole chunk text")
    inspect = sub.add_parser("inspect", help="Load and clean one file and show the result.")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--chars", type=int, default=300, help="preview length per page")
    inspect.add_argument("--chunks", action="store_true", help="also show chunking statistics")
    serve = sub.add_parser("serve", help="Run the HTTP API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    return parser


def _inspect(path: Path, chars: int, show_chunks: bool) -> int:
    try:
        raw = load_document(path)
    except (FileNotFoundError, UnsupportedFileTypeError, DocumentLoadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    doc = clean_document(raw)
    total = sum(len(page.text) for page in doc.pages)
    print(f"{doc.source}: {len(raw.pages)} page(s) loaded, {len(doc.pages)} kept, {total} chars")
    for page in doc.pages:
        preview = page.text[:chars].replace("\n", " / ")
        print(f"--- page {page.number} ({len(page.text)} chars)\n{preview}")
    if show_chunks:
        _print_chunk_stats(doc, chars)
    return 0


def _print_chunk_stats(doc: Document, chars: int) -> None:
    settings = Settings()
    chunks = chunk_document(doc, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        print("no chunks")
        return
    sizes = [len(c.text) for c in chunks]
    print(
        f"\n{len(chunks)} chunks (size={settings.chunk_size}, overlap={settings.chunk_overlap}): "
        f"min {min(sizes)}, avg {sum(sizes) // len(sizes)}, max {max(sizes)} chars"
    )
    for chunk in chunks[:5]:
        preview = chunk.text[:chars].replace("\n", " / ")
        print(f"--- {chunk.chunk_id}\n{preview}")
    if len(chunks) > 5:
        print(f"... and {len(chunks) - 5} more")


def _describe(result: IngestResult) -> str:
    line = f"{result.status:<10} {result.source}"
    if result.status in ("added", "updated"):
        line += f"  ({result.chunks_added} chunks)"
    if result.error:
        line += f"  ({result.error})"
    return line


def _ingest(paths: list[Path], force: bool, prune: bool) -> int:
    settings = Settings()
    service = RagService(settings)
    if prune and paths:
        print("error: --prune only works on the data directory (give no paths)", file=sys.stderr)
        return 2

    counts: Counter[str] = Counter()
    for target in paths or [settings.data_dir]:
        results: Iterator[IngestResult]
        if target.is_dir():
            results = service.ingest_directory(target, force=force, prune=prune)
        elif target.is_file():
            results = iter([_ingest_file(service, target, force)])
        else:
            print(f"error: {target} not found", file=sys.stderr)
            return 2
        for result in results:
            counts[result.status] += 1
            print(_describe(result))

    summary = ", ".join(f"{n} {status}" for status, n in sorted(counts.items())) or "nothing to do"
    print(f"\n{summary}. Index holds {service.index_size()} chunks.")
    return 1 if counts["failed"] else 0


def _components(result: SearchResult) -> str:
    """In hybrid mode, show the two scores behind the fused score."""
    if result.vector_score is None or result.bm25_score is None:
        return ""
    return f"  (cos {result.vector_score:.3f}, bm25 {result.bm25_score:.2f})"


def _search(
    query: str,
    top_k: int | None,
    sources: list[str] | None,
    min_score: float | None,
    mode: str | None,
    full: bool,
) -> int:
    service = RagService(Settings())
    if service.index_size() == 0:
        print("The index is empty. Run `vectornote ingest` first.", file=sys.stderr)
        return 1
    indexed = service.indexed_sources()
    unknown = [name for name in sources or [] if name not in indexed]
    if unknown:
        print(f"error: not indexed: {', '.join(unknown)}", file=sys.stderr)
        print(f"indexed files: {', '.join(indexed)}", file=sys.stderr)
        return 2
    try:
        results = service.search(query, top_k, sources, min_score, mode)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not results:
        print("No results.")
        return 0
    for rank, result in enumerate(results, start=1):
        chunk = result.chunk
        location = f"{chunk.source}, p. {chunk.page}"
        print(f"{rank:>2}. {result.score:.3f}  {location}{_components(result)}")
        body = chunk.text if full else chunk.text[:220].replace("\n", " / ")
        print("    " + body.replace("\n", "\n    "))
    return 0


def _check_sources(service: RagService, sources: list[str] | None) -> int | None:
    """Return an exit code if a requested source is not indexed, else None."""
    indexed = service.indexed_sources()
    unknown = [name for name in sources or [] if name not in indexed]
    if not unknown:
        return None
    print(f"error: not indexed: {', '.join(unknown)}", file=sys.stderr)
    print(f"indexed files: {', '.join(indexed)}", file=sys.stderr)
    return 2


def _print_sources(result: AskResult) -> None:
    if not result.citations:
        return
    label = "Sources" if result.cited else "Related passages (the answer cited none)"
    print(f"\n{label}:")
    for citation in result.citations:
        print(f"  [{citation.number}] {citation.source}, p. {citation.page}")


def _ask(
    question: str,
    top_k: int | None,
    sources: list[str] | None,
    mode: str | None,
    stream: bool,
) -> int:
    service = RagService(Settings())
    if service.index_size() > 0:
        failure = _check_sources(service, sources)
        if failure is not None:
            return failure
    try:
        result = _answer(service, question, top_k, sources, mode, stream)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_sources(result)
    return 0


def _searching(question: str) -> str:
    return f"(searching for: {question})"


def _answer(
    service: RagService,
    question: str,
    top_k: int | None,
    sources: list[str] | None,
    mode: str | None,
    stream: bool,
    history: list[ChatTurn] | None = None,
) -> AskResult:
    """Print the answer (word by word when streaming) and return the final result."""
    if not stream:
        result = service.ask(question, top_k, sources, mode, history)
        if result.standalone_question != question.strip():
            print(_searching(result.standalone_question))
        print(result.answer)
        return result
    printed = False
    try:
        for event in service.ask_stream(question, top_k, sources, mode, history):
            if isinstance(event, QueryEvent):
                print(_searching(event.question))
            elif isinstance(event, TokenEvent):
                print(event.text, end="", flush=True)
                printed = True
            else:
                print() if printed else print(event.result.answer)
                return event.result
    except OllamaError:
        if printed:
            print()  # end the partial answer's line before the error message
        raise
    raise RuntimeError("the answer stream ended without a result")


def _chat(top_k: int | None, sources: list[str] | None, mode: str | None) -> int:
    service = RagService(Settings())
    if service.index_size() == 0:
        print("The index is empty. Run `vectornote ingest` first.", file=sys.stderr)
        return 1
    failure = _check_sources(service, sources)
    if failure is not None:
        return failure
    print("VectorNote chat. Ask about your documents.")
    print("Follow-up questions work. /reset forgets the conversation, /exit quits.\n")
    history: list[ChatTurn] = []
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            continue
        if question in ("/exit", "/quit"):
            return 0
        if question == "/reset":
            history.clear()
            print("(conversation cleared)")
            continue
        try:
            result = _answer(service, question, top_k, sources, mode, True, history)
        except (ValueError, OllamaError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            continue
        _print_sources(result)
        print()
        if result.answered:
            history += [
                ChatTurn(role="user", content=question),
                ChatTurn(role="assistant", content=result.answer),
            ]
            del history[:-12]  # the rewriter only looks at the latest messages anyway


def _eval_scaffold(count: int, seed: int, output: Path, suggest: bool, force: bool) -> int:
    service = RagService(Settings())
    if service.index_size() == 0:
        print("The index is empty. Run `vectornote ingest` first.", file=sys.stderr)
        return 1
    if output.exists() and not force:
        print(f"error: {output} already exists (use --force to overwrite)", file=sys.stderr)
        return 2
    if count <= 0:
        print("error: --count must be positive", file=sys.stderr)
        return 2
    picked = sample_chunks(service.indexed_chunks(), count, seed)
    if suggest:
        print(f"Asking {service.settings.llm_model} for {len(picked)} draft questions...")
    drafts = draft_questions(picked, service.llm if suggest else None)
    write_questions(output, drafts)
    print(f"Wrote {len(drafts)} drafts to {output}.")
    print("Now edit each line:")
    print("  1. write the question the way a student would ask it, in your own words")
    print("  2. set type, language and reference_answer (a sentence or two)")
    print("  3. add every page that answers it to `expected`; add `keywords` if you like")
    print("  4. delete the `passage` and `needs_review` fields")
    print("Save it as eval/questions.jsonl and run `vectornote eval check`.")
    return 0


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _format_counts(counts: Counter[str]) -> str:
    return ", ".join(f"{name} {n}" for name, n in counts.most_common())


def _index_content(
    service: RagService,
) -> tuple[dict[str, set[int]], dict[tuple[str, int], str]]:
    """The pages that have text in each indexed file, and the text of each page."""
    pages: dict[str, set[int]] = {}
    passages: dict[tuple[str, int], str] = {}
    for chunk in service.indexed_chunks():
        pages.setdefault(chunk.source, set()).add(chunk.page)
        key = (chunk.source, chunk.page)
        passages[key] = f"{passages[key]}\n{chunk.text}" if key in passages else chunk.text
    return pages, passages


def _eval_check(path: Path) -> int:
    try:
        questions = load_questions(path)
    except (FileNotFoundError, DatasetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    service = RagService(Settings())
    pages, passages = _index_content(service)
    report = check_questions(questions, pages, passages)

    print(f"{path}: {_plural(report.total, 'question')}")
    if report.total:
        share = round(100 * report.unanswerable / report.total)
        print(
            f"  answerable {report.answerable}, unanswerable {report.unanswerable} ({share}%), "
            f"follow-ups {report.follow_ups}"
        )
        print(f"  types: {_format_counts(report.by_type)}")
        print(f"  languages: {_format_counts(report.by_language)}")
        if report.by_source:
            print(f"  sources: {_format_counts(report.by_source)}")
    for label, items in (("Errors", report.errors), ("Warnings", report.warnings)):
        if items:
            print(f"\n{label} ({len(items)}):")
            for item in items:
                print(f"  - {item}")
    if report.ok and not report.warnings:
        print("\nOK")
    elif report.ok:
        print("\nNo errors (the warnings are advice).")
    return 0 if report.ok else 1


def _eval_run(args: argparse.Namespace) -> int:
    if args.judge and not args.answers:
        print("error: --judge needs --answers", file=sys.stderr)
        return 2
    if args.top_k <= 0:
        print("error: --top-k must be positive", file=sys.stderr)
        return 2
    try:
        questions = load_questions(args.path)
    except (FileNotFoundError, DatasetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not questions:
        print(f"error: {args.path} has no questions", file=sys.stderr)
        return 2
    service = RagService(Settings())
    if service.index_size() == 0:
        print("The index is empty. Run `vectornote ingest` first.", file=sys.stderr)
        return 1
    pages, _ = _index_content(service)
    problems = check_questions(questions, pages).errors
    if problems:
        print(f"{args.path} has errors, so the numbers would be meaningless:", file=sys.stderr)
        for problem in problems[:5]:
            print(f"  - {problem}", file=sys.stderr)
        if len(problems) > 5:
            print(f"  ... and {len(problems) - 5} more", file=sys.stderr)
        print("Run `vectornote eval check` for the full list.", file=sys.stderr)
        return 1

    queries = resolve_queries(service, questions, args.rewrite)
    retrievals = []
    for mode in args.modes or list(MODES):
        print(f"Measuring retrieval ({mode})...", file=sys.stderr)
        retrievals.append(run_retrieval(service, questions, queries, mode, args.top_k))

    answers: AnswerSummary | None = None
    records: list[AnswerRecord] = []
    if args.answers:
        total = len(questions)
        print(f"Asking {total} questions with {service.settings.llm_model}...", file=sys.stderr)

        def progress(done: int, count: int) -> None:
            print(f"  {done}/{count}", end="\r" if done < count else "\n", file=sys.stderr)

        answers, records = run_answers(
            service, questions, args.answer_mode, args.top_k, args.judge, progress=progress
        )

    settings = service.settings
    info = RunInfo(
        questions_file=str(args.path),
        questions=len(questions),
        embedding_model=service.embedder.name,
        llm_model=settings.llm_model,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        min_relevance=settings.min_relevance,
        top_k=args.top_k,
    )
    render = format_markdown if args.format == "markdown" else format_text
    print(render(info, retrievals, answers))
    if args.output is not None:
        write_json(args.output, build_payload(info, retrievals, answers, records))
        print(f"Saved the full results to {args.output}", file=sys.stderr)
    return 0


def _ingest_file(service: RagService, path: Path, force: bool) -> IngestResult:
    try:
        return service.ingest_path(path, force=force)
    except (UnsupportedFileTypeError, DocumentLoadError, OSError) as exc:
        return IngestResult(path.name, "failed", error=str(exc))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return _run(args)
    except (EmbeddingModelMismatchError, EmbedderUnavailableError, OllamaError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.command == "ingest":
        return _ingest(args.paths, args.force, args.prune)
    if args.command == "search":
        return _search(
            args.query, args.top_k, args.sources, args.min_score, args.mode, args.full
        )
    if args.command == "eval":
        if args.eval_command == "scaffold":
            return _eval_scaffold(args.count, args.seed, args.output, args.suggest, args.force)
        if args.eval_command == "run":
            return _eval_run(args)
        return _eval_check(args.path)
    if args.command == "chat":
        return _chat(args.top_k, args.sources, args.mode)
    if args.command == "ask":
        return _ask(
            args.question, args.top_k, args.sources, args.mode, not args.no_stream
        )
    if args.command == "inspect":
        return _inspect(args.path, args.chars, args.chunks)
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "vectornote.api.app:app", host=args.host, port=args.port, reload=args.reload
        )
        return 0
    print(f"'{args.command}' is not implemented yet.")
    return 1
