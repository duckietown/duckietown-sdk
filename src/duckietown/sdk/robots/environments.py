"""Read-only discovery for co-located Duckiematrix replicas."""

__all__ = ["EnvironmentInfo", "discover_environments"]

import math
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from types import MappingProxyType
from typing import Any
from urllib.error import HTTPError

import cbor2

_POSE_AXES = ("x", "y", "z", "roll", "pitch", "yaw")


@dataclass(frozen=True)
class EnvironmentInfo:
    """Immutable identity and placement metadata for a replica.

    The manifest does not advertise strict stepping, run identity,
    camera specifications, or independent episode resets.
    """

    id: str
    index: int
    source_map: str
    isolation: str
    tile_map_keys: tuple[str, ...]
    vehicle_keys: tuple[str, ...]
    entity_keys: tuple[str, ...]
    source_keys: Mapping[str, str]
    pose: Mapping[str, float]


def _read_keys(descriptor: dict[str, Any], field: str) -> tuple[str, ...]:
    keys = descriptor.get(field)
    if (
        not isinstance(keys, list)
        or not keys
        or any(not isinstance(key, str) or not key for key in keys)
        or len(set(keys)) != len(keys)
    ):
        message = f"Environment {field!r} must contain unique nonempty keys."
        raise ValueError(message)
    return tuple(keys)


def _read_environment(identifier: str, descriptor: object) -> EnvironmentInfo:
    if not isinstance(identifier, str) or not identifier:
        message = "Environment IDs must be nonempty strings."
        raise ValueError(message)
    if not isinstance(descriptor, dict):
        message = f"Environment {identifier!r} must be a dictionary."
        raise TypeError(message)
    index = descriptor.get("index")
    source_map = descriptor.get("source_map")
    if type(index) is not int or index < 0:
        message = f"Environment {identifier!r} requires a nonnegative index."
        raise ValueError(message)
    if not isinstance(source_map, str) or not source_map:
        message = f"Environment {identifier!r} requires a source_map."
        raise ValueError(message)
    isolation = descriptor.get("isolation")
    if isolation != "overlap-v1":
        message = f"Unsupported environment isolation {isolation!r}."
        raise ValueError(message)
    tile_maps = _read_keys(descriptor, "tile_map_keys")
    vehicles = _read_keys(descriptor, "vehicle_keys")
    entities = _read_keys(descriptor, "entity_keys")
    sources = descriptor.get("source_keys")
    if (
        not isinstance(sources, dict)
        or set(sources) != set(entities)
        or any(
            not isinstance(key, str) or not key for key in sources.values()
        )
        or len(set(sources.values())) != len(sources)
        or any(key not in entities for key in tile_maps + vehicles)
        or any(
            key != f"{identifier}/{source}"
            for key, source in sources.items()
        )
    ):
        message = (
            f"Environment {identifier!r} has inconsistent entity mappings."
        )
        raise ValueError(message)
    pose = descriptor.get("pose")
    if (
        not isinstance(pose, dict)
        or set(pose) != set(_POSE_AXES)
        or any(
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value != 0
            for value in pose.values()
        )
    ):
        message = "overlap-v1 environments require identity local transforms."
        raise ValueError(message)
    return EnvironmentInfo(
        id=identifier,
        index=index,
        source_map=source_map,
        isolation=isolation,
        tile_map_keys=tile_maps,
        vehicle_keys=vehicles,
        entity_keys=entities,
        source_keys=MappingProxyType(dict(sources)),
        pose=MappingProxyType(dict(pose)),
    )


def discover_environments(
    host: str = "127.0.0.1", port: int = 7501,
) -> tuple[EnvironmentInfo, ...]:
    """Read the Engine's ``map/environments`` replica manifest.

    Results follow numeric indices rather than sorted entity names.
    An empty tuple means the Engine has no replica metadata, including
    legacy Engines without this topic. A topic without a published value
    raises ConnectionError so callers can retry during startup. Network
    errors and malformed metadata raise; callers must not infer replica
    groupings instead.
    """
    url = f"http://{host}:{port}/map/environments/"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
            raw = response.read()
    except HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            return ()
        raise
    if not raw:
        error_message = "Environment manifest is not ready: no value yet."
        raise ConnectionError(error_message)
    message = cbor2.loads(raw)
    if not isinstance(message, dict):
        error_message = "Environment discovery requires a Dictionary message."
        raise TypeError(error_message)
    if not isinstance(message.get("data"), dict):
        error_message = "Environment discovery requires a Dictionary message."
        raise TypeError(error_message)
    environments = [
        _read_environment(identifier, descriptor)
        for identifier, descriptor in message["data"].items()
    ]
    environments.sort(key=lambda environment: environment.index)
    indices = [environment.index for environment in environments]
    if indices != list(range(len(environments))):
        error_message = "Environment indices must be unique and contiguous."
        raise ValueError(error_message)
    entities = [
        key for environment in environments for key in environment.entity_keys
    ]
    if len(set(entities)) != len(entities):
        error_message = "Runtime entity keys must belong to one environment."
        raise ValueError(error_message)
    return tuple(environments)
