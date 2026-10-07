# Laya triage service (docs/LAYA.md §1). Plan 4 GB RAM with both checkpoints.
FROM python:3.12-slim
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir "laya[serve]==0.3.27"
# LAYA_API_KEY must be provided at run time (no auth without it); never bake it in.
ENV LAYA_MODELS=english,multilingual LAYA_PRELOAD=1 LAYA_THREADS=2 LAYA_MAX_CONCURRENT=4 \
    LAYA_MAX_LOADED=2 HF_HOME=/models
VOLUME /models
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["laya-serve"]
