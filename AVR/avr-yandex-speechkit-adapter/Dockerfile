FROM python:3.12-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir pip -q

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PORT=6023
EXPOSE 6023

# avr-app-backend задаёт PORT=6xxx при Run агента — URL в avr-core должен совпадать с фактическим bind
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-6023}"]
