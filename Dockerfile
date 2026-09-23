FROM python:3.11-slim

# Prevent Python from writing .pyc files and force unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN mkdir /app chown 1000:1000 /app
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the client and server scripts into the container
COPY --chown=1000:1000 mcp-client.py .
COPY --chown=1000:1000 mcp-server.py .

# Copy requirements and install via pip
COPY --chown=1000:1000 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


USER 1000

CMD ["python", "mcp-client.py"]

