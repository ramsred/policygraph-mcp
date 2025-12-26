FROM python:3.11-slim

# Why:
# - slim = smaller attack surface
# - python 3.11 = matches rest of stack

WORKDIR /app

# Copy requirements first (layer caching best practice)
COPY services/host/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

# Runtime code and config live at repo root
COPY src /app/src
COPY config /app/config
COPY eval /app/eval

# Default command
CMD ["python", "-m", "src.host.multi_mcp_host"]