FROM python:3.11-slim

WORKDIR /app

# Installer torch CPU uniquement (~200 Mo au lieu de 2.5 Go)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# Installer les autres dépendances
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    psycopg2-binary \
    python-multipart \
    numpy \
    scipy \
    httpx \
    pdfplumber \
    sentence-transformers

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]