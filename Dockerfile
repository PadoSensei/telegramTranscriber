# 1. Use an official Python image
FROM python:3.11-slim

# 2. Install system dependencies
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

# --- NEW: CRITICAL FOR SRC LAYOUT ---
# 6. Tell Python to look for the 'telegram_transcriber' package inside the src directory
ENV PYTHONPATH=/app/src

# 7. Update Healthcheck to match the new process name
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD pgrep -f "telegram_transcriber.main" || exit 1

# 8. Run the bot as a module (Standard for package structures)
CMD ["python", "-m", "telegram_transcriber.main"]