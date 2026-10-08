"""Duckietown SDK middleware."""

__all__ = ["GenericPublisher", "GenericSubscriber"]

from abc import abstractmethod
from collections.abc import Callable
from threading import Event
import time
from typing import Any

import numpy as np
from duckietown_messages.actuators import CarLights, DifferentialPWM
from duckietown_messages.colors import RGBA
from duckietown_messages.standard import Boolean, Header

from duckietown.sdk.types import Component


class GenericNetworkComponent(Component):
    """Generic network component."""

    _host: str
    _path_prefix: str | tuple[str, ...]
    _robot_name: str

    def __init__(
        self,
        host: str,
        robot_name: str,
        path_prefix: str = "",
    ) -> None:
        """Initialize the generic network component.

        Args:
            host (str): The host address of the component.
            robot_name (str): The name of the robot.
            path_prefix (str, optional): The path prefix for the
            component. Defaults to `""`.

        """
        super().__init__()
        self._host = host
        self._robot_name = robot_name
        self._path_prefix = path_prefix


class GenericPublisher(GenericNetworkComponent):
    """Generic publisher."""

    @abstractmethod
    def publish(self, data: Any) -> None:  # noqa: ANN401
        """Publish data.

        Args:
            data (Any): The data to publish.

        Raises:
            ValueError: If the data is invalid.

        """


class GenericSubscriber[T](GenericNetworkComponent):
    """Generic subscriber."""

    _callbacks: set[Callable[[Any], None]]
    _event: Event
    _reading: T | None
    _reading_used: bool

    def __init__(
        self,
        host: str,
        robot_name: str,
        path_prefix: str = "",
    ) -> None:
        """Initialize the generic subscriber.

        Args:
            host (str): The host address of the component.
            robot_name (str): The name of the robot.
            path_prefix (str, optional): The path prefix for the
            component. Defaults to `""`.

        """
        super().__init__(host, robot_name, path_prefix)
        # async behavior
        self._callbacks = set()
        # sync behavior
        self._reading = None
        self._reading_used = False
        self._event = Event()

    def _callback(self, message: Any) -> None:  # noqa: ANN401
        data = self._unpack(message)
        # notify sync readers
        self._reading = data
        self._reading_used = False
        self._event.set()
        # perform async callbacks
        for callback in self._callbacks:
            callback(data)

    def _grab_current(self) -> T | None:
        if self._reading_used:
            return None
        self._reading_used = True
        return self._reading

    @abstractmethod
    def _unpack(self, message: Any) -> Any:  # noqa: ANN401
        pass

    def attach(self, callback: Callable[[Any], None]) -> None:
        """Attach a callback to the subscriber.

        Args:
            callback (Callable[[Any], None]): The callback to attach.

        """
        self._callbacks.add(callback)

    def detach(self, callback: Callable[[Any], None]) -> None:
        """Detach a callback from the subscriber.

        Args:
            callback (Callable[[Any], None]): The callback to detach.

        """
        self._callbacks.remove(callback)

    @property
    def latest(self) -> T | None:
        """Get the latest reading.

        Returns:
            T | None: The latest reading or `None` if not available.

        """
        return self._reading

    def get(
        self,
        *,
        block: bool = False,
        clean_up: bool = False,
        timeout: float | None = None,
    ) -> T | None:
        """Get the latest reading.

        Args:
            block (bool, optional): Whether to block until a reading is
            available. Defaults to `False`.
            clean_up (bool, optional): Whether to stop the
            subscriber after getting the reading. Defaults to `False`.
            timeout (float | None, optional): The timeout for blocking
            behavior. Defaults to `None`.

        Returns:
            T | None: The latest reading or `None` if not available.

        """
        if not self.has_started:
            self.start()
        if block:
            if not self._event.wait(timeout):
                return None
            self._event.clear()
        data = self._grab_current()
        if clean_up:
            self.stop()
        return data


class CameraDriver(GenericSubscriber[np.ndarray]):
    """Camera component."""


class DeltaTDriver(GenericSubscriber):
    """Delta time component."""


class InertialMeasurementUnit(GenericSubscriber):
    """Inertial measurement unit component."""


class LEDsDriver(GenericPublisher):
    """Lights component."""

    car_lights: CarLights

    def __init__(
        self,
        host: str,
        _: int,
        robot_name: str,
        __: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the lights component."""
        super().__init__(
            host,
            robot_name,
            **kwargs,
        )
        front_left = RGBA(r=1, g=1, b=1, a=0.2)
        front_right = RGBA(r=1, g=1, b=1, a=0.2)
        back_left = RGBA(r=1, g=0, b=0, a=0.2)
        back_right = RGBA(r=1, g=0, b=0, a=0.2)
        self.car_lights = CarLights(
            front_left=front_left,
            front_right=front_right,
            back_left=back_left,
            back_right=back_right,
        )

    def publish(self, _: Any) -> None:  # noqa: ANN401
        """Publish the given data.

        Args:
            _ (Any): The data to publish.

        """

    def set(  # noqa: PLR0913
        self,
        front_left_rgba: tuple[float, float, float, float],
        front_right_rgba: tuple[float, float, float, float],
        back_left_rgba: tuple[float, float, float, float],
        back_right_rgba: tuple[float, float, float, float],
        header: Header | None = None,
        *,
        publish: bool = True,
    ) -> None:
        """Set the lights pattern.

        Args:
            front_left_rgba (tuple[float, float, float, float]): The
            color of the front left light.
            front_right_rgba (tuple[float, float, float, float]): The
            color of the front right light.
            back_left_rgba (tuple[float, float, float, float]): The
            color of the back left light.
            back_right_rgba (tuple[float, float, float, float]): The
            color of the back right light.
            header (Header | None, optional): The message header. If
            `None`, a new header with the current timestamp will be
            created. Defaults to `None`.
            publish (bool, optional): Whether to publish the message.
            Defaults to `True`.

        Raises:
            ValueError: If any of the RGBA values are not in the
            range [0, 1].

        """
        for rgba in (
            front_left_rgba,
            front_right_rgba,
            back_left_rgba,
            back_right_rgba,
        ):
            for value in rgba:
                if not 0 <= value <= 1:
                    message = "RGBA values must be in the range [0, 1]."
                    raise ValueError(message)
        front_left_rgba_list = list(front_left_rgba)
        front_right_rgba_list = list(front_right_rgba)
        back_left_rgba_list = list(back_left_rgba)
        back_right_rgba_list = list(back_right_rgba)
        if header is None:
            timestep = time.time()
            header = Header(timestamp=timestep)
        front_left = RGBA.from_list(front_left_rgba_list, header)
        front_right = RGBA.from_list(front_right_rgba_list, header)
        back_left = RGBA.from_list(back_left_rgba_list, header)
        back_right = RGBA.from_list(back_right_rgba_list, header)
        self.car_lights.header = header
        self.car_lights.front_left = front_left
        self.car_lights.front_right = front_right
        self.car_lights.back_left = back_left
        self.car_lights.back_right = back_right
        if publish:
            self.publish(self.car_lights)


class MapLayerDriver(GenericSubscriber):
    """Map layer component."""


class MotorsDriver(GenericPublisher):
    """Motors component."""

    differential_pwm: DifferentialPWM

    def __init__(
        self,
        host: str,
        _: int,
        robot_name: str,
        __: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the motors component."""
        super().__init__(
            host,
            robot_name,
            **kwargs,
        )
        self.differential_pwm = DifferentialPWM(left=0, right=0)

    def publish(self, _: Any) -> None:  # noqa: ANN401
        """Publish the given data.

        Args:
            _ (Any): The data to publish.

        """

    def set(
        self,
        left: float,
        right: float,
        header: Header | None = None,
        *,
        publish: bool = True,
    ) -> None:
        """Set the PWM signals for the motors.

        Args:
            left (float): The PWM signal for the left motor.
            right (float): The PWM signal for the right motor.
            header (Header | None, optional): The message header. If
            `None`, a new header with the current timestamp will be
            created. Defaults to `None`.
            publish (bool, optional): Whether to publish the message.
            Defaults to `True`.

        Raises:
            ValueError: If the PWM signals are not in the range
            `[-1, 1]`.

        """
        if not -1 <= left <= 1 or not -1 <= right <= 1:
            message = "PWM signals must be in the the range [-1, 1]."
            raise ValueError(message)
        if header is None:
            timestep = time.time()
            header = Header(timestamp=timestep)
        self.differential_pwm.header = header
        self.differential_pwm.left = left
        self.differential_pwm.right = right
        if publish:
            self.publish(self.differential_pwm)


class PoseDriver(GenericSubscriber):
    """Pose component."""


class ResetFlagDriver(GenericPublisher):
    """State reset flag component."""

    boolean: Boolean

    def __init__(
        self,
        host: str,
        _: int,
        robot_name: str,
        __: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the state reset flag component."""
        super().__init__(
            host,
            robot_name,
            **kwargs,
        )
        self.boolean = Boolean(data=False)

    def publish(self, _: Any) -> None:  # noqa: ANN401
        """Publish the given data.

        Args:
            _ (Any): The data to publish.

        """

    def set(
        self,
        header: Header | None = None,
        *,
        data: bool = True,
        publish: bool = True,
    ) -> None:
        """Set the state reset flag.

        Args:
            header (Header | None, optional): The message header. If
            `None`, a new header with the current timestamp will be
            created. Defaults to `None`.
            data (bool, optional): Whether to reset the state. Defaults
            to `True`.
            publish (bool, optional): Whether to publish the message.
            Defaults to `True`.

        """
        if header is None:
            timestep = time.time()
            header = Header(timestamp=timestep)
        self.boolean.header = header
        self.boolean.data = data
        if publish:
            self.publish(self.boolean)


class TimeOfFlightDriver(GenericSubscriber):
    """Time-of-flight sensor component."""


class Twist(GenericSubscriber):
    """Twist component."""


class WheelEncoderDriver(GenericSubscriber):
    """Wheel encoder component."""


class WorldInput(GenericSubscriber):
    """World input component."""

    current_session_id: int | None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the world input component."""
        super().__init__(*args, **kwargs)
        self.current_session_id = None

    def _remember_session_id(self, message: Any) -> None:
        if not isinstance(message, dict):
            self.current_session_id = None
            return
        session_id = message.get("session_id")
        self.current_session_id = (
            session_id if isinstance(session_id, int) else None
        )


class WorldOutput(GenericPublisher):
    """World output component."""
