"""Command-line interface for VectorNote."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from vectornote import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vectornote",
        description="Offline RAG study assistant.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("ingest", help="Ingest documents from the data directory.")
    ask = sub.add_parser("ask", help="Ask a question about your documents.")
    ask.add_argument("question")
    serve = sub.add_parser("serve", help="Run the HTTP API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "vectornote.api.app:app", host=args.host, port=args.port, reload=args.reload
        )
        return 0
    print(f"'{args.command}' is not implemented yet.")
    return 1
