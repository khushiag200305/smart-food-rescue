"""Entry point.

Local:  flask --app run init-db   then   flask --app run run --debug
EC2:    gunicorn -w 3 -b 127.0.0.1:8000 run:app
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
