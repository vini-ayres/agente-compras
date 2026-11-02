FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "httpx>=0.28.0" \
    "mcp>=1.26.0" \
    "pydantic>=2.0.0" \
    "pydantic-settings>=2.0.0" \
    "uvicorn[standard]>=0.32.0"

COPY src ./src

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
