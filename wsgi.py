"""WSGI vstupní bod (PythonAnywhere: Web → WSGI configuration file importuje `application`)."""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app import create_app  # noqa: E402

app = create_app()
application = app

if __name__ == "__main__":
    app.run()
