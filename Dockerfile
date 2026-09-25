FROM python:3.12-slim
WORKDIR /src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/src/api:/src

# Same image serves three roles in production (Railway/Fly): the web process (this default
# CMD), the RQ worker, and each scheduled task — see DEPLOY.md for the exact start commands
# Railway needs for the worker service and the cron-job services. Migrations run automatically
# on web-process startup (app/main.py's lifespan, skipped only when APP_ENV=test).
EXPOSE 8000
CMD ["sh", "-c", "cd api && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
