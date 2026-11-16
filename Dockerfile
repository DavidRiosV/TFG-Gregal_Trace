# Imagen de la web de Gregal Trace (Django + Gunicorn)
# Se construye con:  docker compose build

# Linux ligero con Python 3.12, la misma versión que el entorno virtual del proyecto
FROM python:3.12-slim

# Python no guarda archivos .pyc y escribe los mensajes al momento (se ven en docker compose logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# Primero solo requirements.txt: si no cambia, Docker reutiliza esta capa y no reinstala los paquetes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Después el resto del proyecto (lo que excluye .dockerignore no se copia)
COPY . .

# Gunicorn escucha en el puerto 8000 dentro del contenedor
EXPOSE 8000

# Orden por defecto. En docker-compose.yml se antepone migrate y collectstatic
CMD ["gunicorn", "mysite.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
