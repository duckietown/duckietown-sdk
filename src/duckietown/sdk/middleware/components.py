"""Duckietown SDK middleware drivers."""

import time
from typing import Any, TypeVar

import numpy as np
from duckietown_messages.actuators import CarLights, DifferentialPWM
from duckietown_messages.colors import RGBA
from duckietown_messages.standard import Boolean, Header

from duckietown.sdk.middleware.base import GenericPublisher, GenericSubscriber

T = TypeVar("T")


class Camera(GenericSubscriber[np.ndarray]):
    """Camera component."""


class Collision(GenericSubscriber):
    """Collision component."""


class DeltaTime(GenericSubscriber):
    """Delta time component."""


class InertialMeasurementUnit(GenericSubscriber):
    """Inertial measurement unit component."""


class Lights(GenericPublisher):
    """Lights component."""

    car_lights: CarLights

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        topic: tuple[str, ...],
        **kwargs: Any,
    ) -> None:
        """Initialize the lights component."""
        super().__init__(
            host=host,
            port=port,
            robot_name=robot_name,
            topic=topic,
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

    def set(
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


class MapLayer(GenericSubscriber):
    """Map layer component."""


class Motors(GenericPublisher):
    """Motors component."""

    differential_pwm: DifferentialPWM

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        topic: tuple[str, ...],
        **kwargs: Any,
    ) -> None:
        """Initialize the motors component."""
        super().__init__(
            host=host,
            port=port,
            robot_name=robot_name,
            topic=topic,
            **kwargs,
        )
        self.differential_pwm = DifferentialPWM(left=0, right=0)

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
            message = "PWM signals must be in the range [-1, 1]."
            raise ValueError(message)
        if header is None:
            timestep = time.time()
            header = Header(timestamp=timestep)
        self.differential_pwm.header = header
        self.differential_pwm.left = left
        self.differential_pwm.right = right
        if publish:
            self.publish(self.differential_pwm)


class Pose(GenericSubscriber):
    """Pose component."""


class StateResetFlag(GenericPublisher):
    """State reset flag component."""

    boolean: Boolean

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        topic: tuple[str, ...],
        **kwargs: Any,
    ) -> None:
        """Initialize the state reset flag component."""
        super().__init__(
            host=host,
            port=port,
            robot_name=robot_name,
            topic=topic,
            **kwargs,
        )
        self.boolean = Boolean(data=False)

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


class TimeOfFlightSensor(GenericSubscriber):
    """Time-of-flight sensor component."""


class Twist(GenericSubscriber):
    """Twist component."""


class WheelEncoder(GenericSubscriber):
    """Wheel encoder component."""


class WorldInput(GenericSubscriber):
    """World input component."""


class WorldOutput(GenericPublisher):
    """World output component."""
