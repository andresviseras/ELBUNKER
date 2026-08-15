# Usar una imagen oficial de Python ligera
FROM python:3.11-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del backend y frontend
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Añadimos la carpeta backend al path de Python para que reconozca el módulo "app"
ENV PYTHONPATH=/app/backend

# Exponer el puerto dinámico
EXPOSE ${PORT:-8000}

# Comando para ejecutar la aplicación con el directorio base correcto
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]