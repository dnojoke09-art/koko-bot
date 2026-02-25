# Use Python 3.13 slim as base
FROM python:3.13-slim

# Install system dependencies for building Python packages
RUN apt-get update && \
    apt-get install -y gcc g++ make libffi-dev libssl-dev python3-dev build-essential && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Run the bot
CMD ["python", "main.py"]
