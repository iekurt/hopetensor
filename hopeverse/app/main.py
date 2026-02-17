from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- DB Bootstrap ---
from app.db.base import Base
from app.db.session import engine

# --- Routers ---
from app.identity.router import router as identity_router


app = FastAPI(
    title="HOPEverse Core",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None
)


# --- Startup: create tables (v1 only) ---
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health Check ---
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "hopeverse-core",
        "version": "1.0.0"
    }


# --- Identity Router ---
app.include_router(identity_router, prefix="/v1/did", tags=["did"])


# --- Root ---
@app.get("/")
def root():
    return {
        "message": "HOPEverse Execution Phase v1 is running"
    }