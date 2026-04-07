"""Generic vehicle base class."""

__all__ = ["GenericVehicle"]

from typing import Any

from duckietown_messages.simulation import WorldEntityOutput

from duckietown.sdk.components import CompoundComponent
from duckietown.sdk.middleware.components import (
    DeltaTime,
    MapLayer,
)
from duckietown.sdk.middleware.dtps.components import (
    DTPSDeltaTime,
    DTPSMapLayer,
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
                environment-controlled stepping path. Requires
                *simulated* to be ``True``. Defaults to ``False``.

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
            if self._simulated and not self._gym_mode:
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

    def make_world_entity_output(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> WorldEntityOutput:
        """Build a per-entity gym WorldOutput payload.

        Gym world messages are environment-owned. Vehicle classes can
        override this hook to describe how their per-entity actuator
        payload should be constructed.
        """
        raise NotImplementedError

    def _map_layer(self, name: str) -> MapLayer:
        return self._get_component(
            "map_layer",
            name,
            (),
            MapLayer,
            DTPSMapLayer,
        )

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
        if self._simulated:
            self.map_frames.start()
            self.map_tile_info.start()
            self.map_tiles.start()
        self.has_started = True

    def stop(self) -> None:
        """Stop vehicle components for the current mode."""
        if self._simulated:
            self.map_frames.stop()
            self.map_tile_info.stop()
            self.map_tiles.stop()
        self.has_started = False
