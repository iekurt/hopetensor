import os
from fastapi import FastAPI

ENV = os.getenv("ENV", "dev")

app = FastAPI(
    docs_url=None if ENV == "prod" else "/docs",
    redoc_url=None if ENV == "prod" else "/redoc",
    openapi_url=None if ENV == "prod" else "/openapi.json",
)

@app.get("/health")
def health():
    return {"status": "ok"}


