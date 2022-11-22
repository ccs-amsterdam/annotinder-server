
web: gunicorn annotinder.api:app --workers 8 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-5000}