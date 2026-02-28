FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir librosa tensorflow-cpu
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the BirdNET model during build so startup is faster
RUN python -c "from birdnetlib.analyzer import Analyzer; Analyzer()"

COPY server.py .

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "120", "--workers", "1", "server:app"]
