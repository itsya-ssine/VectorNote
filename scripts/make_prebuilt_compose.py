"""Write docker-compose.prebuilt.yml: the same stack as docker-compose.yml, but running the
images published on ghcr.io instead of building them, so nothing needs to be cloned or built.

    uv run python scripts/make_prebuilt_compose.py            # rewrite the file
    uv run python scripts/make_prebuilt_compose.py --check    # fail if it is out of date

A test runs the check, so the two compose files cannot drift apart.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docker-compose.yml"
TARGET = ROOT / "docker-compose.prebuilt.yml"

REGISTRY = "ghcr.io/itsya-ssine"
IMAGES = {
    "    build: .": f"    image: {REGISTRY}/vectornote-api:${{VECTORNOTE_VERSION:-latest}}",
    "    build: ./web": f"    image: {REGISTRY}/vectornote-web:${{VECTORNOTE_VERSION:-latest}}",
}
HEADER = """\
# GENERATED from docker-compose.yml by scripts/make_prebuilt_compose.py. Do not edit.
#
# Runs the published images, so nothing is built and you do not need the source code:
#
#   mkdir -p data && curl -O https://raw.githubusercontent.com/itsya-ssine/VectorNote/main/docker-compose.prebuilt.yml
#   docker compose -f docker-compose.prebuilt.yml up
#
# Then open http://localhost:3000. The first start downloads the language model (about 2 GB).
# VECTORNOTE_VERSION=1.0.0 pins a release; the default is the latest one.

"""  # noqa: E501


def render(source: str) -> str:
    """The prebuilt compose file for the text of docker-compose.yml."""
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("name:"))
    body: list[str] = []
    for line in lines[start:]:
        body.append(IMAGES.get(line.rstrip(), line))
    result = "\n".join(body) + "\n"
    missing = [old for old in IMAGES if old not in source]
    if missing:
        raise SystemExit(f"docker-compose.yml no longer has: {', '.join(missing)}")
    return HEADER + result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only check, do not write")
    args = parser.parse_args()

    expected = render(SOURCE.read_text())
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != expected:
            print(f"{TARGET.name} is out of date: run scripts/make_prebuilt_compose.py")
            return 1
        return 0
    TARGET.write_text(expected)
    print(f"wrote {TARGET.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
