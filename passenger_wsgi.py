import sys
import os


def application(environ, start_response):
    status = "200 OK"
    headers = [("Content-Type", "text/html; charset=UTF-8")]
    start_response(status, headers)
    return [b"HOPEverse temporary WSGI OK"]

# path fix (çok kritik)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# debug için
with open(os.path.join(BASE_DIR, "debug.log"), "w") as f:
    f.write("WSGI START\n")

try:
    from a2wsgi import ASGIMiddleware
    from app import app as fastapi_app

    application = ASGIMiddleware(fastapi_app)

    with open(os.path.join(BASE_DIR, "debug.log"), "a") as f:
        f.write("APP LOADED OK\n")

except Exception as e:
    with open(os.path.join(BASE_DIR, "debug.log"), "a") as f:
        f.write(f"ERROR: {str(e)}\n")
    raise
