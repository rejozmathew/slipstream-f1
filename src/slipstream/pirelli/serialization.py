"""Deterministic JSON serialization helpers for immutable Pirelli contracts."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum


def jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value
