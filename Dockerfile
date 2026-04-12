FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
ENV APP_MODULE=coordinator:app

CMD ["sh", "-lc", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT}"]
