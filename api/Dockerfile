# Image of the prediction API and the web dashboard, served with uvicorn.
# Build it from the root of the repository:
#   docker build -f api/Dockerfile -t accidentes-api .
# Run it with the model folder mounted read-only:
#   docker run --rm -p 127.0.0.1:8021:8080 -v "$PWD/data:/data:ro" accidentes-api
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY src ./src
COPY api ./api
COPY dashboard ./dashboard

# The service does not need root
RUN useradd --create-home --uid 10001 api
USER api

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
