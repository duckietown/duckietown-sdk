"""Duckietown Postal Service (DTPS) middleware drivers."""

import math
import time
from typing import Any

import numpy as np
from duckietown_messages.actuators import CarLights, DifferentialPWM
from duckietown_messages.colors import RGBA
from duckietown_messages.standard import Boolean

from duckietown.sdk.middleware.components import (
    Camera,
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
from duckietown.sdk.middleware.dtps.base import (
    GenericDTPSPublisher,
    GenericDTPSSubscriber,
)
from duckietown.sdk.utils.jpeg import JPEG


class DTPSCamera(Camera, GenericDTPSSubscriber):
    """DTPS camera component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        name: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS camera component."""
        super().__init__(
            host=host,
            port=port,
            robot_name=robot_name,
            topic=("sensor", "camera", name, "jpeg"),
            **kwargs,
        )

    def _unpack(self, message: dict) -> np.ndarray:
        jpeg: bytes = message["data"]
        return JPEG.decode(jpeg)


class DTPSDeltaTime(DeltaTime, GenericDTPSSubscriber):
    """DTPS delta time component."""

    def __init__(
        self,
        host: str,
        port: int,
        _: str,
        __: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS delta time component."""
        super().__init__(
            host,
            port,
            "",
            ("delta_time",),
            **kwargs,
        )

    def _unpack(self, message: dict) -> float:
        return message["data"]


class DTPSInertialMeasurementUnit(
    InertialMeasurementUnit,
    GenericDTPSSubscriber,
):
    """DTPS inertial measurement unit component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        name: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS inertial measurement unit component."""
        super().__init__(
            host,
            port,
            robot_name,
            ("sensor", "imu", name, "all"),
            **kwargs,
        )

    def _unpack(self, message: dict) -> dict:
        return message["data"]


class DTPSLights(Lights, GenericDTPSPublisher):
    """DTPS lights component."""

    _idle: CarLights
    _off: RGBA

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        actuator_name: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS lights component."""
        GenericDTPSPublisher.__init__(
            self,
            host=host,
            port=port,
            robot_name=robot_name,
            topic=("actuator", "lights", actuator_name, "pattern"),
            **kwargs,
        )
        front_left = RGBA(r=1, g=1, b=1, a=0.2)  # White
        front_right = RGBA(r=1, g=1, b=1, a=0.2)  # White
        back_right = RGBA(r=1, g=0, b=0, a=0.2)  # Red
        back_left = RGBA(r=1, g=0, b=0, a=0.2)  # Red
        self._idle = CarLights(
            front_left=front_left,
            front_right=front_right,
            back_right=back_right,
            back_left=back_left,
        )
        self._off = RGBA(r=0, g=0, b=0, a=0)

    def _stop(self) -> None:
        self.publish(self._idle)
        time.sleep(0.1)


class DTPSMapLayer(MapLayer, GenericDTPSSubscriber):
    """DTPS map layer component."""

    def __init__(
        self,
        host: str,
        port: int,
        _: str,
        name: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS map layer component."""
        super().__init__(
            host,
            port,
            "",
            ("map", name),
            **kwargs,
        )

    def _unpack(self, message: dict) -> dict:
        return message


class DTPSMotors(Motors, GenericDTPSPublisher):
    """DTPS motors component."""

    _OFF = 0

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        actuator_name: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS motors component."""
        GenericDTPSPublisher.__init__(
            self,
            host=host,
            port=port,
            robot_name=robot_name,
            topic=("actuator", "wheels", actuator_name, "pwm_filtered"),
            **kwargs,
        )
        self.differential_pwm = DifferentialPWM(left=0, right=0)

    def _stop(self) -> None:
        data = DifferentialPWM(left=self._OFF, right=self._OFF)
        self._override_message = data
        # send the 0, 0 command multiple times
        for _ in range(5):
            self.publish(data)
            time.sleep(1 / 60)


class DTPSPose(Pose, GenericDTPSSubscriber):
    """DTPS pose component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        _: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS pose component."""
        super().__init__(
            host,
            port,
            robot_name,
            ("state", "pose"),
            **kwargs,
        )

    def _unpack(self, message: dict) -> dict[str, dict[str, float] | float]:
        timestamp: float = message["header"]["timestamp"]
        position: dict[str, float] = message["position"]
        rotation: dict[str, float] = message["rotation"]
        return {
            "timestamp": timestamp,
            "position": {
                "x": position["x"],
                "y": position["y"],
                "z": position["z"],
            },
            "rotation": {
                "w": rotation["w"],
                "x": rotation["x"],
                "y": rotation["y"],
                "z": rotation["z"],
            },
        }


class DTPSStateResetFlag(StateResetFlag, GenericDTPSPublisher):
    """DTPS state reset flag component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        _: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS state reset flag component."""
        GenericDTPSPublisher.__init__(
            self,
            host=host,
            port=port,
            robot_name=robot_name,
            topic=("state", "reset"),
            **kwargs,
        )
        self.boolean = Boolean(data=False)


class DTPSTimeOfFlightSensor(TimeOfFlightSensor, GenericDTPSSubscriber):
    """DTPS time-of-flight sensor component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        name: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """DTPS the time-of-flight sensor component."""
        super().__init__(
            host,
            port,
            robot_name,
            ("sensor", "time_of_flight", name, "range"),
            **kwargs,
        )

    def _unpack(self, message: dict) -> float:
        return message["data"]


class DTPSTwist(Twist, GenericDTPSSubscriber):
    """DTPS twist component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        _: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS twist component."""
        super().__init__(
            host,
            port,
            robot_name,
            ("state", "twist"),
            **kwargs,
        )

    def _unpack(self, message: dict) -> dict[str, dict[str, float] | float]:
        timestamp: float = message["header"]["timestamp"]
        linear_velocity: dict[str, float] = message["linear_velocity"]
        angular_velocity: dict[str, float] = message["angular_velocity"]
        return {
            "timestamp": timestamp,
            "linear_velocity": {
                "x": linear_velocity["x"],
                "y": linear_velocity["y"],
                "z": linear_velocity["z"],
            },
            "angular_velocity": {
                "x": angular_velocity["x"],
                "y": angular_velocity["y"],
                "z": angular_velocity["z"],
            },
        }


class DTPSWheelEncoder(WheelEncoder, GenericDTPSSubscriber):
    """DTPS wheel encoder component."""

    _RESOLUTION = 135

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        name: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS wheel encoder component.

        Args:
            host (str): The host address.
            port (int): The port number.
            robot_name (str): The robot name.
            name (str): The wheel name (either "left" or "right").
            **kwargs: Additional keyword arguments passed to the
            parent constructor.

        Raises:
            ValueError: If the wheel name is not recognized.

        """
        if name not in ["left", "right"]:
            message = (
                f"Side '{name}' not recognized. Valid choices are "
                "['left', 'right']."
            )
            raise ValueError(message)
        super().__init__(
            host,
            port,
            robot_name,
            ("sensor", "wheel_encoder", name, "ticks"),
            **kwargs,
        )

    @property
    def resolution(self) -> int:
        """Get the resolution of the wheel encoder.

        Returns:
            int: The resolution of the wheel encoder.

        """
        return DTPSWheelEncoder._RESOLUTION

    def _unpack(self, message: dict) -> float:
        ticks: int = message["data"]
        rotations = ticks / self.resolution
        return 2 * math.pi * rotations


class DTPSWorldInput(WorldInput, GenericDTPSSubscriber):
    """DTPS world input component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        _: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS world input component."""
        super().__init__(
            host,
            port,
            robot_name,
            ("in",),
            **kwargs,
        )

    def _unpack(self, message: dict) -> dict:
        self._remember_session_id(message)
        return message


class DTPSWorldOutput(WorldOutput, GenericDTPSPublisher):
    """DTPS world output component."""

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        _: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the DTPS world output component."""
        super().__init__(
            host,
            port,
            robot_name,
            ("out",),
            **kwargs,
        )
