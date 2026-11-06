"""Simulated entity and engine-discovery utilities."""

__all__ = ["SimulatedEntity", "discover_entities", "wait_for_simulation"]

import re
import time
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from urllib.error import URLError

import cbor2

from duckietown.sdk.middleware.dtps.components import DTPSWorldInput

_ENGINE_HOST = "127.0.0.1"
_ENGINE_PORT = 7501
_GYM_WORLD_TOPIC_NAME = "gym"


def discover_entities(
    host: str = _ENGINE_HOST,
    port: int = _ENGINE_PORT,
) -> tuple[list[str], list[str]]:
    """Query the engine's DTPS index and classify entities.

    Returns:
        ``(vehicle_names, static_names)`` - vehicles have both a
        ``robot/<name>/in`` and a ``robot/<name>/out`` topic; static
        entities (watchtowers, traffic lights, Duckiecams) have only
        ``robot/<name>/in``.

    Raises:
        ``OSError`` / ``URLError`` if the engine is not reachable.

    """
    url = f"http://{host}:{port}/"
    with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
        raw = resp.read()
    topics_wire = cbor2.loads(raw)
    topics: set[str] = set(topics_wire.get("topics", {}).keys())
    pattern = re.compile(r"^robot/(.+)/in$")
    vehicles: list[str] = []
    statics: list[str] = []
    for topic in topics:
        match = pattern.match(topic)
        if not match:
            continue
        name = match.group(1)
        if name == _GYM_WORLD_TOPIC_NAME:
            continue
        if f"robot/{name}/out" in topics:
            vehicles.append(name)
        else:
            statics.append(name)
    return sorted(vehicles), sorted(statics)


def wait_for_simulation(
    host: str = _ENGINE_HOST,
    port: int = _ENGINE_PORT,
    timeout: float = 120,
) -> tuple[list[str], list[str]]:
    """Block until the engine exposes at least one vehicle.

    Polls :py:func:`discover_entities` once per second until a vehicle
    appears or *timeout* seconds have elapsed.

    Returns:
        ``(vehicle_names, static_names)`` as returned by
        :py:func:`discover_entities` once the engine is ready.

    Raises:
        ``TimeoutError`` if no vehicles appear within *timeout* seconds.

    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with suppress(OSError, URLError):
            vehicle_names, static_names = discover_entities(host, port)
            if vehicle_names:
                return vehicle_names, static_names
        time.sleep(1)
    msg = (
        f"Engine at {host}:{port} did not expose any vehicles "
        f"within {timeout}s."
    )
    raise TimeoutError(msg)


class SimulatedEntity:
    """A read-only simulated entity that streams sensor data.

    This class represents any entity in the Duckiematrix that publishes
    a ``WorldInput`` stream (``robot/<name>/in``) but has no actuators -
    for example a watchtower, traffic light, or Duckiecam.

    Use :py:meth:`attach` to register a callback that fires each
    time the engine sends a new sensor frame.

    Example::

        wt = SimulatedEntity("map_0/watchtower_0")

        def on_frame(world_input: dict) -> None:
            image = world_input["compressed_image"]["data"]
            ...

        wt.attach(on_frame)
        wt.start()
        ...
        wt.stop()
    """

    def __init__(
        self,
        name: str,
        host: str = _ENGINE_HOST,
        port: int = _ENGINE_PORT,
    ) -> None:
        """Initialize the simulated entity.

        Args:
            name: The entity name as it appears in the engine map
                (e.g. ``"map_0/watchtower_0"``).
            host: Engine host. Defaults to ``"127.0.0.1"``.
            port: Engine DTPS port. Defaults to ``7501``.

        """
        self._name = name
        self._world_input = DTPSWorldInput(
            host,
            port,
            name,
            "",
            path_prefix=("robot",),
        )

    @property
    def name(self) -> str:
        """The entity name."""
        return self._name

    def attach(self, callback: Callable[[Any], None]) -> None:
        """Register a callback for incoming sensor frames.

        Args:
            callback: Called with the raw ``WorldInput`` dict
                each cycle.

        """
        self._world_input.attach(callback)

    def start(self) -> None:
        """Start receiving sensor data from the engine."""
        self._world_input.start()

    def stop(self) -> None:
        """Stop receiving sensor data."""
        self._world_input.stop()
