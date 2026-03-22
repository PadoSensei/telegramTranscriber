# 1. Use an official Python image
FROM python:3.11-slim

# 2. Install system dependencies (ffmpeg for Whisper, git for Obsidian Sync)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# 3. Set the working directory
WORKDIR /app

# 4. Copy requirements and install Python libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code
COPY . .

# 6. Run the bot
CMD ["python", "main.py"]