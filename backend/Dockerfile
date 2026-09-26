FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY atlas ./atlas
COPY migrations ./migrations
COPY start.sh ./start.sh
RUN pip install .

# Never run as root.
RUN useradd --create-home --uid 10001 atlas
USER atlas

EXPOSE 8000
# The same image runs the API (default, see start.sh) or the worker (python -m atlas.worker).
CMD ["./start.sh"]
