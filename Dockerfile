FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create directories for Prover9-Mace4
RUN mkdir -p /app/src/bin

# Set environment variables
ENV PYTHONPATH=/app
ENV PATH="/app/src/bin:${PATH}"

# Expose ports
EXPOSE 8000  # FastAPI server
EXPOSE 8080  # Web GUI

# Default command (can be overridden)
CMD ["python", "api_server.py"] 