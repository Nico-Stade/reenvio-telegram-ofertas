FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Crear directorio de estado
RUN mkdir -p data

# En Docker se recomienda usar SESSION_STRING (headless)
# Generalo con: python main.py --gen-session
CMD ["python", "main.py"]
