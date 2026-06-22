FROM python:3.12-slim

# Dependencias del sistema para PyMuPDF / Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates

EXPOSE 8000

# 4 workers gunicorn con hilos (maneja varias personas a la vez)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", \
     "--timeout", "60", "--access-logfile", "-", "app:app"]
