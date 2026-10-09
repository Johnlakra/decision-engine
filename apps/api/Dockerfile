# syntax=docker/dockerfile:1
# Build context is the REPO ROOT (copies niches/ and schemas/):
#   docker build -f apps/api/Dockerfile .
# Layout inside the image mirrors the repo so app.core.config.REPO_ROOT resolves:
#   /srv/apps/api/app, /srv/niches, /srv/schemas

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=0 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv/apps/api
# Dependencies first (cached until pyproject/uv.lock change).
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
# Size budget: drop bytecode caches, type stubs and vendored tests.
# (litellm.proxy cannot be removed: litellm imports it at load time.)
RUN find /opt/venv -depth \( -name __pycache__ -o -name tests \) -exec rm -r {} + \
 && find /opt/venv -name '*.pyi' -delete
# Unused transitive deps (pulled by litellm; no S3 / HF tokenizer paths are used here).
RUN cd /opt/venv/lib/python3.12/site-packages \
 && rm -rf boto3* botocore* s3transfer* hf_xet* huggingface_hub*

FROM python:3.12-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/srv/apps/api \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /srv --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv/apps/api
COPY --chown=app:app --chmod=755 apps/api/ ./
COPY --chown=app:app niches/ /srv/niches/
COPY --chown=app:app schemas/ /srv/schemas/
COPY --chown=app:app data/free_tiers.yaml data/stacks.yaml /srv/data/
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
