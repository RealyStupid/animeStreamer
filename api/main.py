"""
    API main entrance point allowing the setup and deployment of the API
"""
from fastapi import FastAPI

from core.config import get_settings

settings = get_settings()