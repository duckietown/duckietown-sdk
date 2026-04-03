"""Generic vehicle base class."""

__all__ = ["GenericVehicle"]

import os
from collections.abc import Callable
from typing import Any

from duckietown_messages.simulation import WorldOutput as WorldOutputMessage
from duckietown_messages.standard import Header

from duckietown.sdk.components import CompoundComponent
from duckietown.sdk.middleware.components import (
    DeltaTime,
    MapLayer,
    WorldInput,
    WorldOutput,
)
from duckietown.sdk.middleware.dtps.components import (
    DTPSDeltaTime,
    DTPSMapLayer,
    DTPSWorldInput,
    DTPSWorldOutput,
)
from duckietown.sdk.middleware.shm.components import (
    ShmWorldInput,
    ShmWorldOutput,
)

_DEFAULT_REAL_PORT = 11911
_DEFAULT_SIMULATED_PORT = 7501


class GenericVehicle(CompoundComponent):
    """Generic vehicle.

    Base class for every vehicle type.
    """

    _gym_mode: bool
    _host: str
    _name: str
    _port: int
    _simulated: bool
    has_started: bool
    world_output: WorldOutputMessage

    def __init__(
        self,
        name: str,
        *,
        host: str = "",
        port: int | None = None,
        simulated: bool = False,
        gym_mode: bool = False,
    ) -> None:
        """Initialise the generic vehicle.

        Args:
            name (str): The vehicle's name (used to resolve its host and
                DTPS topics).
            host (str, optional): Host address. Defaults to
                ``"127.0.0.1"`` when *simulated*, otherwise
                ``"<name>.local"``.
            port (int | None, optional): DTPS port. Defaults to ``7501``
                when *simulated*, otherwise ``11911``.
            simulated (bool, optional): Whether the vehicle runs inside
                a Duckiematrix engine. Defaults to ``False``.
            gym_mode (bool, optional): Whether to use the gym-mode
                world-input / world-output loop. Requires *simulated*
                to be ``True``. Defaults to ``False``. Defaults to
                ``False``.

        Raises:
            ValueError: If *gym_mode* is ``True`` but
                *simulated* is ``False``.

        """
        if gym_mode and not simulated:
            message = "Gym mode requires simulated=True."
            raise ValueError(message)
        super().__init__({})
        self._name = name
        self._host = host or ("127.0.0.1" if simulated else f"{name}.local")
        if port is None:
            self._port = (
                _DEFAULT_SIMULATED_PORT if simulated else _DEFAULT_REAL_PORT
            )
        else:
            self._port = port
        self._simulated = simulated
        self._gym_mode = gym_mode
        header = Header()
        self.world_output = WorldOutputMessage(header=header)
        self.has_started = False

    def __repr__(self) -> str:
        """Return a string representation of the vehicle.

        Returns:
            str: Human-readable vehicle description.

        """
        cls = type(self).__name__
        return (
            f"{cls}(name='{self._name}', host='{self._host}', "
            f"port='{self._port}', simulated={self._simulated})"
        )

    def _get_component(
        self,
        kind: str,
        name: str,
        path_prefix: tuple[str, ...],
        cls: type,
        component_cls: type,
    ) -> Any:  # noqa: ANN401
        key = (kind, name)
        if key not in self._components:
            kwargs = {}
            if self._simulated and (
                not self._gym_mode
                or cls in (DeltaTime, WorldInput, WorldOutput)
            ):
                kwargs["path_prefix"] = path_prefix
            self._components[key] = component_cls(
                self._host,
                self._port,
                self._name,
                name,
                **kwargs,
            )
        component = self._components[key]
        if not isinstance(component, cls):
            raise TypeError
        return component

    def _prepare_world_output(self, timestamp: float) -> None:
        session_id = self._world_input.current_session_id
        if session_id is None:
            message = (
                "Cannot publish WorldOutput before receiving a WorldInput "
                "with a session_id."
            )
            raise RuntimeError(message)
        self.world_output.header.timestamp = timestamp
        self.world_output.session_id = session_id

    def _map_layer(self, name: str) -> MapLayer:
        return self._get_component(
            "map_layer",
            name,
            (),
            MapLayer,
            DTPSMapLayer,
        )

    @property
    def _world_input(self) -> WorldInput:
        # Use the shared-memory subscriber whenever DTSHELL_SHM_PATH is
        # set.
        if os.environ.get("DTSHELL_SHM_PATH", ""):
            return self._get_component(
                "in",
                "",
                ("robot",),
                WorldInput,
                ShmWorldInput,
            )
        return self._get_component(
            "in",
            "",
            ("robot",),
            WorldInput,
            DTPSWorldInput,
        )

    @property
    def _world_output(self) -> WorldOutput:
        # Use the shared-memory publisher whenever DTSHELL_SHM_PATH is
        # set.
        if os.environ.get("DTSHELL_SHM_PATH", ""):
            return self._get_component(
                "out",
                "",
                ("robot",),
                WorldOutput,
                ShmWorldOutput,
            )
        return self._get_component(
            "out",
            "",
            ("robot",),
            WorldOutput,
            DTPSWorldOutput,
        )

    def attach(self, callback: Callable[[Any], None]) -> None:
        """Attach a callback to the world input (gym only).

        Args:
            callback (Callable[[Any], None]): Callback called
                with each world-input dict.

        Raises:
            RuntimeError: If not in gym mode.

        """
        if not self._gym_mode:
            message = "Attach can only be called in gym mode."
            raise RuntimeError(message)
        self._world_input.attach(callback)

    def detach(self, callback: Callable[[Any], None]) -> None:
        """Detach a callback from the world input (gym only).

        Args:
            callback (Callable[[Any], None]): Callback to
                detach.

        Raises:
            RuntimeError: If not in gym mode.

        """
        if not self._gym_mode:
            message = "Detach can only be called in gym mode."
            raise RuntimeError(message)
        self._world_input.detach(callback)

    @property
    def delta_time(self) -> DeltaTime:
        """Return the delta time component.

        Returns:
            DeltaTime: The delta time component.

        """
        return self._get_component(
            "delta_time",
            "",
            ("map",),
            DeltaTime,
            DTPSDeltaTime,
        )

    @property
    def map_frames(self) -> MapLayer:
        """Return the map frames component.

        Returns:
            MapLayer: The map frames component.

        """
        return self._map_layer("frames")

    @property
    def map_tile_info(self) -> MapLayer:
        """Return the map tile info component.

        Returns:
            MapLayer: The map tile info component.

        """
        return self._map_layer("tile_maps")

    @property
    def map_tiles(self) -> MapLayer:
        """Return the map tiles component.

        Returns:
            MapLayer: The map tiles component.

        """
        return self._map_layer("tiles")

    def start(self) -> None:
        """Start vehicle components for the current mode."""
        if self._gym_mode:
            self.delta_time.start()
            self._world_output.start()
            self._world_input.start()
        if self._simulated:
            self.map_frames.start()
            self.map_tile_info.start()
            self.map_tiles.start()
        self.has_started = True

    def stop(self) -> None:
        """Stop vehicle components for the current mode."""
        if self._gym_mode:
            self.delta_time.stop()
            self._world_input.stop()
            self._world_output.stop()
        if self._simulated:
            self.map_frames.stop()
            self.map_tile_info.stop()
            self.map_tiles.stop()
        self.has_started = False
