FROM python:3.11

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3-dev \
    gcc \
    g++ \
    i2c-tools \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "System_capture1.py"]
