# One image for both the API and the worker; the command decides which one runs.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY evals ./evals
COPY scripts ./scripts
RUN pip install --upgrade pip && pip install .

# Run as a non-root user.
RUN useradd --create-home evalassist
USER evalassist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
