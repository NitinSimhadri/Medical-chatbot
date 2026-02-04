FROM python:3.10-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# 🔥 BUILD-TIME embeddings download (IMPORTANT)
RUN python - <<EOF
from src.helper import download_hugging_face_embeddings
print("Downloading embeddings at build time...")
download_hugging_face_embeddings()
print("Embeddings cached successfully")
EOF

EXPOSE 8080

CMD ["python", "app.py"]
