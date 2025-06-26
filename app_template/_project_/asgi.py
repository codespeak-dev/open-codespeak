"""
ASGI config for the project.

This configuration creates a FastAPI app and mounts Django as a sub-application.
"""

import os
import django
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', '{{ project_name }}.settings')
django.setup()

# Import after Django setup
from django.core.wsgi import get_wsgi_application
from web.views import app as fastapi_app

# Create the main FastAPI application
app = FastAPI(title="{{ project_name }} API", version="1.0.0")

# Mount the API routes from web.views
app.mount("/api", fastapi_app)

# Mount Django at root for admin interface and other Django features
django_app = get_wsgi_application()
app.mount("/", WSGIMiddleware(django_app))

# Export for uvicorn
application = app
