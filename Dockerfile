FROM python:3.10-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache. This will copy
# `requirements.txt` and `requirements-llm.txt` if present.
COPY requirements*.txt .

# Install dependencies. If `requirements-llm.txt` exists, install it too.
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && if [ -f requirements-llm.txt ]; then pip install --no-cache-dir -r requirements-llm.txt; fi

# Copy application source
COPY . .

# Use environment port 8080 and expose it
ENV PORT=8080
EXPOSE 8080

# Use gunicorn for more reliable production serving if available, fallback to python
CMD ["sh", "-c", "if command -v gunicorn >/dev/null 2>&1; then gunicorn -b 0.0.0.0:$PORT app:app; else python app.py; fi"]
