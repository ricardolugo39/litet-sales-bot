FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY decision_dashboard_v2/requirements.txt /app/decision_dashboard_v2/requirements.txt
RUN pip install --no-cache-dir -r /app/decision_dashboard_v2/requirements.txt

COPY decision_dashboard_v2 /app/decision_dashboard_v2

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} decision_dashboard_v2.wsgi:app"]
