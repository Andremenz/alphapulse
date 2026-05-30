FROM python:3.13-slim

WORKDIR /app

# Install system build dependencies (REQUIRED for ckzg and other packages)
RUN apt-get update && apt-get install -y \
    build-essential \
    make \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for persistent storage
RUN mkdir -p /data

# Expose port for Streamlit
EXPOSE 7860

# Start via start.sh (dual-process wrapper)
CMD ["bash", "start.sh"]
