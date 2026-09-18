FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir "fastapi>=0.110.0" "uvicorn>=0.28.0" "python-multipart>=0.0.9" "typer>=0.9.0" "rich>=13.0.0" "pydantic-settings>=2.0.0"

COPY src/ ./src
COPY docker-compose.yml .

EXPOSE 8000

CMD ["uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
