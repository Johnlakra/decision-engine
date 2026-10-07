"""FastAPI application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the app. Routers are added in later steps."""
    return FastAPI(title="Decision Engine API", version="0.1.0")


app = create_app()
