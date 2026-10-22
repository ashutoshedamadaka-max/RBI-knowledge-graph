FROM python:3.12-slim
WORKDIR /service
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/install_corpus_release.py --archive data/releases/corpus-v2.zip --checksum-file data/releases/corpus-v2.zip.sha256 --data-dir /service/data
ENV DATA_DIR=/service/data POSTGRES_SCHEMA=rbi_corpus_v2 VECTOR_BACKEND=postgres ANSWER_PROVIDER=openai
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
