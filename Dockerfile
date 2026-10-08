FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml README.md ./
COPY src ./src
COPY deploy/constraints.txt ./deploy/constraints.txt
RUN pip install --no-cache-dir --constraint deploy/constraints.txt .
COPY --chmod=0644 alembic.ini ./
COPY --chmod=0755 alembic ./alembic
USER 10001:10001
CMD ["python", "-m", "research_os.cli", "live"]
