"""Serializzazione generica dataclass ⇄ dict (JSON), con tipi annidati e liste."""
from __future__ import annotations

import dataclasses
import types
import typing
from typing import Any


def to_dict(obj: Any) -> Any:
    return dataclasses.asdict(obj)


def from_dict(cls, data: Any) -> Any:
    if data is None or not dataclasses.is_dataclass(cls):
        return data
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        kwargs[f.name] = _conv(hints[f.name], data[f.name])
    return cls(**kwargs)


def _conv(tp, v):
    if v is None:
        return None
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        for a in typing.get_args(tp):
            if a is type(None):
                continue
            return _conv(a, v)
    if origin is list:
        (a,) = typing.get_args(tp)
        return [_conv(a, x) for x in v]
    if dataclasses.is_dataclass(tp):
        return from_dict(tp, v)
    return v
