#!/bin/bash
# Startup script for deployment platforms

# Set default port if not provided
export PORT=${PORT:-5000}

# Check if we're in a container or local environment
if [ -f /.dockerenv ]; then
    echo "Running in Docker container"
    python app.py
else
    echo "Running locally or on platform"
    # Use gunicorn for production, python for development
    if [ "$FLASK_ENV" = "production" ]; then
        gunicorn --bind 0.0.0.0:$PORT --workers 4 --timeout 120 app:app
    else
        python app.py
    fi
fi

