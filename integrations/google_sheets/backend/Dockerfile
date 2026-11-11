# Build from repository root: docker build -f integrations/google_sheets/backend/Dockerfile .
FROM python:3.12-slim
WORKDIR /app
COPY integrations/google_sheets/backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services /app/services
COPY integrations/google_sheets/backend /app
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
