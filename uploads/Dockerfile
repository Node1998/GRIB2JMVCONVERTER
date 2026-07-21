# Native eccodes required by cfgrib -> Docker runtime on Render.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libeccodes-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 1 worker: ingest lock + status are in-process (see README scaling note).
# 600s timeout covers a full model pull; HTTP trigger itself returns in <1s.
CMD ["gunicorn", "-w", "1", "-t", "600", "-b", "0.0.0.0:8000", "app:app"]
