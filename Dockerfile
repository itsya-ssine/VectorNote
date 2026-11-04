# syntax=docker/dockerfile:1

# VectorNote API. Build: `docker build -t vectornote-api .` (or use docker compose).
# Only pyproject.toml, uv.lock, README.md and src/ are sent to the build (see .dockerignore),
# so your documents and your index can never end up in the image.

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/opt/hf
WORKDIR /app

# 1. The locked dependencies, with the CPU build of PyTorch. The default PyPI wheel of torch
#    pulls in about 4 GB of CUDA libraries that are useless in a container without a GPU.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --no-dev --no-emit-project --locked --no-hashes -o /tmp/requirements.txt \
 && TORCH_VERSION="$(sed -n 's/^torch==\([^ ;]*\).*/\1/p' /tmp/requirements.txt)" \
 && test -n "$TORCH_VERSION" \
 && grep -Ev '^(nvidia-|cuda-|triton|torch==)' /tmp/requirements.txt > /tmp/requirements-cpu.txt \
 && uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python --no-deps -r /tmp/requirements-cpu.txt \
 && uv pip install --python /opt/venv/bin/python --no-deps \
        --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}"

# 2. VectorNote itself.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-deps .

# 3. The embedding model, downloaded once at build time so the running container needs no network.
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2docker compose config -q && echo "compose file ok"
RUN /opt/venv/bin/python -c "import sys; from sentence_transformers import SentenceTransformer; SentenceTransformer(sys.argv[1])" "$EMBEDDING_MODEL"


FROM python:3.12-slim
RUN useradd --create-home --uid 1000 vectornote \
 && mkdir /data /chroma \
 && chown vectornote:vectornote /data /chroma
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=vectornote:vectornote /opt/hf /opt/hf

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    VECTORNOTE_DATA_DIR=/data \
    VECTORNOTE_CHROMA_DIR=/chroma
USER vectornote
WORKDIR /home/vectornote
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["vectornote", "serve", "--host", "0.0.0.0", "--port", "8000"]
