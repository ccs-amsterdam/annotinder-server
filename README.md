# AnnoTinder Python backend

A Python backend for the AnnoTinder client, using FastAPI and SQLAlchemy.

Note that this is in active development, so please don't use it as this point.

# DB

Annotinder uses a Postgres DB. For testing and development it's easiers to just fire up a docker image.

```bash
docker run --name postgres -e POSTGRES_USER="devuser" -e POSTGRES_PASSWORD="devpw" -p 5432:5432 -d postgres
```

# Authentication

The current implementation will be removed, and replaced by MiddleCat.
