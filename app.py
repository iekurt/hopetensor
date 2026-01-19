# app.py
from fastapi import FastAPI
from main.core import fastapi_routes, APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION)
fastapi_routes(app)
