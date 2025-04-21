FROM python:3.9-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY src/ /app/src/
COPY web_app.py .
COPY flask_app.py .

# Make sure the binaries are executable
RUN chmod +x /app/src/bin/*

# Create a directory for saved files
RUN mkdir -p /app/saved

# Expose the port
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application with Flask in production mode for better performance
CMD ["python", "flask_app.py", "--port", "8080", "--production"] 