#!/usr/bin/env bash
# Compare chunk sizes: index the same documents once per size, then run `eval run`.
#
#   scripts/bench_chunks.sh                 # sizes 400, 800 and 1200
#   scripts/bench_chunks.sh 600 1000        # your own sizes
#
# Each size gets its own index in .bench/ (git-ignored), so your normal chroma_db/ is not
# touched. The overlap is one eighth of the chunk size. Results are written as Markdown to
# eval/results/chunks-<size>.md and printed at the end.
set -euo pipefail

cd "$(dirname "$0")/.."
sizes=("$@")
if [ ${#sizes[@]} -eq 0 ]; then
  sizes=(400 800 1200)
fi

mkdir -p .bench eval/results
for size in "${sizes[@]}"; do
  overlap=$((size / 8))
  echo "== chunk size $size, overlap $overlap ==" >&2
  export VECTORNOTE_CHUNK_SIZE="$size"
  export VECTORNOTE_CHUNK_OVERLAP="$overlap"
  export VECTORNOTE_CHROMA_DIR=".bench/chroma_$size"
  uv run vectornote ingest --force
  uv run vectornote eval run --format markdown > "eval/results/chunks-$size.md"
done

for size in "${sizes[@]}"; do
  echo
  echo "### Chunk size $size"
  cat "eval/results/chunks-$size.md"
done
