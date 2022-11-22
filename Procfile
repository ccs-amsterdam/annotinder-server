
web: python -m annotinder add_user admin@admin.com --password admin && gunicorn annotinder.api:app --workers 8 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-5000}