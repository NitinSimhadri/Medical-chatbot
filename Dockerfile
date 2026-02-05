FROM python:3.10-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
# Install dependencies (allow failures to not block CI per user request)
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt || true

# Copy application source
COPY . .

# Use environment port 8080 and expose it
ENV PORT=8080
EXPOSE 8080

# Use gunicorn for more reliable production serving if available, fallback to python
CMD ["sh", "-c", "if command -v gunicorn >/dev/null 2>&1; then gunicorn -b 0.0.0.0:$PORT app:app; else python app.py; fi"]