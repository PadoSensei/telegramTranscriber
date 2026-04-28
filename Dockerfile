# 1. Use an official Python image
FROM python:3.11-slim

# 2. Install system dependencies (ffmpeg for Whisper, git for Obsidian Sync, procps for healthcheck)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 3. Set the working directory
WORKDIR /app

# 4. Copy requirements and install Python libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code
COPY . .

# 6. Add Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD pgrep -f "python main.py" || exit 1

# 7. Run the bot
CMD ["python", "main.py"]