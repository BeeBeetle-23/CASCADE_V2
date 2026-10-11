FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY sample_docs ./sample_docs
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/cascade.db UPLOAD_DIR=/data/uploads
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
# Tables and the demo application are created/seeded on startup (idempotent).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
