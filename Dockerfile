FROM python:3.10-slim

# Set timezone to IST (Optional: helpful for system logs)
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install system dependencies for OpenCV/GLib
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install CPU-only Torch (Lighter, <200MB instead of 800MB+)
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Run the bot
CMD ["python", "main.py"]
