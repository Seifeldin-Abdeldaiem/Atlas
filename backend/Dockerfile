FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY atlas ./atlas
COPY migrations ./migrations
RUN pip install .

# Never run as root.
RUN useradd --create-home --uid 10001 atlas
USER atlas

EXPOSE 8000
# The same image runs the API (default) or the worker (python -m atlas.worker).
CMD ["uvicorn", "atlas.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
