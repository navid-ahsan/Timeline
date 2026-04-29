FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY sql/ ./sql/
COPY front/ ./front/
COPY manage.py ./
COPY timeline_project/ ./timeline_project/
COPY apps/ ./apps/
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh

ENV PYTHONPATH=/app/src
ENV DJANGO_SETTINGS_MODULE=timeline_project.settings

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
