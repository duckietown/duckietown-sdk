"""Generic Duckiebot."""

from collections.abc import Callable
from typing import Any

from duckietown_messages.simulation import WorldOutput as WorldOutputMessage
from duckietown_messages.standard import Header

from duckietown.sdk.components import CompoundComponent
from duckietown.sdk.middleware.components import (
    Camera,
    Collision,
    DeltaTime,
    InertialMeasurementUnit,
    Lights,
    MapLayer,
    Motors,
    Pose,
    StateResetFlag,
    TimeOfFlightSensor,
    Twist,
    WheelEncoder,
    WorldInput,
    WorldOutput,
)
from duckietown.sdk.middleware.dtps.components import (
    DTPSCamera,
    DTPSCollision,
    DTPSDeltaTime,
    DTPSInertialMeasurementUnit,
    DTPSLights,
    DTPSMapLayer,
    DTPSMotors,
    DTPSPose,
    DTPSStateResetFlag,
    DTPSTimeOfFlightSensor,
    DTPSTwist,
    DTPSWheelEncoder,
    DTPSWorldInput,
    DTPSWorldOutput,
)

DEFAULT_ROBOT_SWITCHBOARD_PORT = 11911
DEFAULT_DUCKIEMATRIX_PORT = 7501


class GenericDuckiebot(CompoundComponent):
    """Generic Duckiebot.

    This class provides a generic interface for Duckiebot models,
    allowing access to various hardware drivers and components.
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
        """Initialize the generic Duckiebot.

        Args:
            name (str): The name of the Duckiebot.
            host (str, optional): The host address of the Duckiebot.
            Defaults to `""`.
            port (int | None, optional): The port number for the
            Duckiebot. Defaults to `None`.
            simulated (bool, optional): Whether the Duckiebot is
            simulated. Defaults to `False`.
            gym_mode (bool, optional): Whether to start in gym mode.
            Defaults to `False`.

        Raises:
            ValueError: If `simulated` is `False` and `gym_mode` is
            `True`.

        """
        if gym_mode and not simulated:
            message = "Gym mode is only available for simulated Duckiebots."
            raise ValueError(message)
        super().__init__({})
        self._name = name
        self._host = host or ("127.0.0.1" if simulated else f"{name}.local")
        if port is None:
            self._port = (
                DEFAULT_ROBOT_SWITCHBOARD_PORT
                if not simulated
                else DEFAULT_DUCKIEMATRIX_PORT
            )
        else:
            self._port = port
        self._simulated = simulated
        self._gym_mode = gym_mode
        header = Header()
        self.world_output = WorldOutputMessage(header=header)

    def __repr__(self) -> str:
        """Return the string representation of generic Duckiebot.

        Returns:
            str: The string representation of the Duckiebot.

        """
        return (
            f"GenericDuckiebot(name='{self._name}', host='{self._host}', "
            f"port='{self._port}', simulated={self._simulated})"
        )

    def _camera(self, name: str) -> Camera:
        return self._get_component(
            "camera",
            name,
            ("robot",),
            Camera,
            DTPSCamera,
        )

    def _get_component(
        self,
        kind: str,
        name: str,
        path_prefix: tuple[str, ...],
        cls: type,
        component_cls: type,
    ) -> Any:
        key = (kind, name)
        component = self._components.get(key)
        if component is None:
            kwargs = {}
            if self._simulated and (
                not self._gym_mode
                or cls in (DeltaTime, WorldInput, WorldOutput)
            ):
                kwargs["path_prefix"] = path_prefix
            component = component_cls(
                self._host,
                self._port,
                self._name,
                name,
                **kwargs,
            )
            self._components[key] = component
        if not isinstance(component, cls):
            component_class = type(component)
            message = (
                f"Expected component of type {cls.__name__}, got "
                f"{component_class.__name__}"
            )
            raise TypeError(message)
        return component

    def _inertial_measurement_unit(self, name: str) -> InertialMeasurementUnit:
        return self._get_component(
            "inertial_measurement_unit",
            name,
            ("robot",),
            InertialMeasurementUnit,
            DTPSInertialMeasurementUnit,
        )

    def _lights(self, name: str) -> Lights:
        return self._get_component(
            "lights",
            name,
            ("robot",),
            Lights,
            Lights if self._gym_mode else DTPSLights,
        )

    def _map_layer(self, name: str) -> MapLayer:
        return self._get_component(
            "map_layer",
            name,
            (),
            MapLayer,
            DTPSMapLayer,
        )

    def _motors(self, name: str) -> Motors:
        return self._get_component(
            "motors",
            name,
            ("robot",),
            Motors,
            Motors if self._gym_mode else DTPSMotors,
        )

    def _time_of_flight_sensor(
        self,
        name: str,
    ) -> TimeOfFlightSensor:
        return self._get_component(
            "time_of_flight_sensor",
            name,
            ("robot",),
            TimeOfFlightSensor,
            DTPSTimeOfFlightSensor,
        )

    def _wheel_encoder(self, name: str) -> WheelEncoder:
        return self._get_component(
            "wheel_encoder",
            name,
            ("robot",),
            WheelEncoder,
            DTPSWheelEncoder,
        )

    @property
    def _world_input(self) -> WorldInput:
        return self._get_component(
            "in",
            "",
            ("robot",),
            WorldInput,
            DTPSWorldInput,
        )

    @property
    def _world_output(self) -> WorldOutput:
        return self._get_component(
            "out",
            "",
            ("robot",),
            WorldOutput,
            DTPSWorldOutput,
        )

    def attach(self, callback: Callable[[Any], None]) -> None:
        """Attach a callback to the world input (gym mode only).

        Args:
            callback (Callable[[Any], None]): The callback to attach.

        Raises:
            RuntimeError: If the method is called when not in gym mode.

        """
        if not self._gym_mode:
            message = "Attach can only be called in gym mode."
            raise RuntimeError(message)
        self._world_input.attach(callback)

    @property
    def collision(self) -> Collision:
        """Return the collision component.

        Returns:
            Collision: The collision component.

        """
        return self._get_component(
            "collision",
            "",
            ("robot",),
            Collision,
            DTPSCollision,
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

    def detach(self, callback: Callable[[Any], None]) -> None:
        """Detach a callback from the world input (gym mode only).

        Args:
            callback (Callable[[Any], None]): The callback to detach.

        Raises:
            RuntimeError: If the method is called when not in gym mode.

        """
        if not self._gym_mode:
            message = "Detach can only be called in gym mode."
            raise RuntimeError(message)
        self._world_input.detach(callback)

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

    @property
    def pose(self) -> Pose:
        """Return the pose component.

        Returns:
            Pose: The pose component.

        """
        return self._get_component(
            "pose",
            "",
            ("robot",),
            Pose,
            DTPSPose,
        )

    def start(self) -> None:
        """Start all the components of the Duckiebot."""
        if self._gym_mode:
            self.delta_time.start()
            self._world_input.start()
            self._world_output.start()
        else:
            self.pose.start()
            self.twist.start()
            self.state_reset_flag.start()
        self.map_frames.start()
        self.map_tile_info.start()
        self.map_tiles.start()
        self.has_started = True

    def stop(self) -> None:
        """Stop all the components of the Duckiebot."""
        if self._gym_mode:
            self.delta_time.stop()
            self._world_input.stop()
            self._world_output.stop()
        else:
            self.pose.stop()
            self.twist.stop()
            self.state_reset_flag.stop()
        self.map_frames.stop()
        self.map_tile_info.stop()
        self.map_tiles.stop()
        self.has_started = False

    @property
    def state_reset_flag(self) -> StateResetFlag:
        """Return the state reset flag component.

        Returns:
            StateResetFlag: The state reset flag component.

        """
        return self._get_component(
            "state_reset_flag",
            "",
            ("robot",),
            StateResetFlag,
            StateResetFlag if self._gym_mode else DTPSStateResetFlag,
        )

    @property
    def twist(self) -> Twist:
        """Return the twist component.

        Returns:
            Twist: The twist component.

        """
        return self._get_component(
            "twist",
            "",
            ("robot",),
            Twist,
            DTPSTwist,
        )
