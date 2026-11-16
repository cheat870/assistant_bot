# Production 24/7 Docker Container for Telegram Assistant Bot
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    HOME=/home/user

# Install ffmpeg (required for audio/video processing), nodejs (YouTube JS solver) and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set up non-root user (UID 1000) required by Hugging Face Spaces
RUN useradd -m -u 1000 user
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source code and set permissions
COPY . .
RUN mkdir -p /app/downloads && chown -R user:user /app /home/user

USER user

# Expose ports (7860 for Hugging Face Spaces, 8080 for Render/Koyeb)
EXPOSE 7860 8080

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Run the bot
CMD ["python", "main.py"]
