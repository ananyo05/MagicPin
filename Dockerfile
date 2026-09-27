FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Never ship a host-specific venv or caches into the image
RUN rm -rf .venv __pycache__ engine/__pycache__ tests/__pycache__ .pytest_cache

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
