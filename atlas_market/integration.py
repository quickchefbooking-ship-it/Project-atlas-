"""Fail-closed application mounting helper for the synthetic market watchlist.

Production composition must provide its authentication dependency explicitly.
This module does not import the application's auth implementation.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, FastAPI

from .api import router


def mount_market_watchlist_router(
    app: FastAPI,
    *,
    authentication_dependency: Callable[..., Any],
) -> FastAPI:
    """Mount the synthetic market router behind an explicit auth dependency.

    The dependency is mandatory to avoid accidental unauthenticated mounting
    through the production helper. Return the app to support composition tests.
    """
    if not callable(authentication_dependency):
        raise TypeError("A callable authentication dependency is required.")

    app.include_router(
        router,
        dependencies=[Depends(authentication_dependency)],
    )
    return app
