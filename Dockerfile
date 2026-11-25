FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código del compilador, reglas, interfaz web y galería de ejemplos.
COPY *.py reglas.json ./
COPY backends/ backends/
COPY web/ web/
COPY ejemplos/ ejemplos/
COPY pruebas/ pruebas/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "SERVIRCOR:app", "--host", "0.0.0.0", "--port", "8000"]
