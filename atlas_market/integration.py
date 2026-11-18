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

    Reject path collisions before mutating the application so a repeated or
    conflicting composition cannot silently register duplicate market routes.
    """
    if not callable(authentication_dependency):
        raise TypeError("A callable authentication dependency is required.")

    incoming_paths = {
        route.path for route in router.routes if getattr(route, "path", None) is not None
    }
    existing_paths = {
        route.path for route in app.routes if getattr(route, "path", None) is not None
    }
    conflicts = sorted(incoming_paths & existing_paths)
    if conflicts:
        raise ValueError(
            "Market watchlist route path already registered: " + ", ".join(conflicts)
        )

    app.include_router(
        router,
        dependencies=[Depends(authentication_dependency)],
    )
    return app
