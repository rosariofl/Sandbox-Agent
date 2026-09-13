FROM python:3.11-slim

RUN mkdir /app
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Prevent Python from writing .pyc files and force unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy the client and server scripts into the container
COPY mcp-client.py .
COPY mcp-server.py .

# Copy requirements and install via pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "mcp-client.py"]

