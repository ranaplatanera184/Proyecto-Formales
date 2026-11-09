FROM python:3.13-slim

WORKDIR /app

COPY main.py .
COPY Token.py .
COPY ImplementacionAnalisisLexico.py .
COPY AnalisisSintactico.py .
COPY semantico.py .
COPY expresiones.py .
COPY schematico.py .
COPY gestor_reglas.py .
COPY almacenamiento.py .
COPY reglas.json .
COPY SERVIRCOR.py .
COPY jace_app.py .
COPY web/ web/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "SERVIRCOR:app", "--host", "0.0.0.0", "--port", "8000"]