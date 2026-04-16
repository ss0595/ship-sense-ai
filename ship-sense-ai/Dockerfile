FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN mkdir -p /app/logs /app/data

EXPOSE 8000

CMD ["python", "-B", "app.py", "--host", "0.0.0.0", "--port", "8000"]
