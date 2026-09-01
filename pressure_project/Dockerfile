FROM python:3.9-bullseye

WORKDIR /app

# Install system dependencies for I2C
RUN apt-get update && apt-get install -y \
    i2c-tools \
    libgpiod2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

CMD ["python3", "system_convert.py"]
