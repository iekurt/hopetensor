from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.get("/health")
def health():
    return {"status": "ok"}
    
    
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

import os
from fastapi.middleware.cors import CORSMiddleware

allowed = os.getenv("CORS_ORIGINS", "")
origins = [x.strip() for x in allowed.split(",") if x.strip()]

if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
        allow_headers=["*"],
    )

import os
from fastapi import Header, HTTPException

API_KEY = os.getenv("API_KEY")

def require_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/")
def root():
    return {"status": "HOPE"}

