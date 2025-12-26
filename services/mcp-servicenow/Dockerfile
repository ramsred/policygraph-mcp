FROM python:3.11-slim

RUN useradd -m appuser
WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src
USER appuser

EXPOSE 8000
CMD ["python", "-m", "src.server"]
