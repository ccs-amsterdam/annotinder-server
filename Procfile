
web: gunicorn annotinder.api:app --workers 6 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-5000}