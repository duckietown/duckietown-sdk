"""DB21M Duckiebot."""

import time

from duckietown.sdk.middleware.components import (
    Camera,
    InertialMeasurementUnit,
    Lights,
    Motors,
    TimeOfFlightSensor,
    WheelEncoder,
)
from duckietown.sdk.robots.duckiebot.generic import GenericDuckiebot


class DB21M(GenericDuckiebot):
    """DB21M Duckiebot.

    This class represents the DB21M model of Duckiebot, extending the
    GenericDuckiebot base class.
    """

    def _set_car_lights(
        self,
        front_left_rgba: tuple[float, float, float, float] | None,
        front_right_rgba: tuple[float, float, float, float] | None,
        back_left_rgba: tuple[float, float, float, float] | None,
        back_right_rgba: tuple[float, float, float, float] | None,
    ) -> None:
        if (
            front_left_rgba is not None
            or front_right_rgba is not None
            or back_left_rgba is not None
            or back_right_rgba is not None
        ):
            if (
                front_left_rgba is None
                or front_right_rgba is None
                or back_left_rgba is None
                or back_right_rgba is None
            ):
                message = "If any light color is set, all must be set."
                raise ValueError(message)
            self.lights.set(
                front_left_rgba,
                front_right_rgba,
                back_left_rgba,
                back_right_rgba,
                self.world_output.header,
                publish=False,
            )
            self.world_output.car_lights = self.lights.car_lights
        else:
            self.world_output.car_lights = None

    def _set_differential_pwm(
        self,
        left_pwm: float | None,
        right_pwm: float | None,
    ) -> None:
        if left_pwm is not None:
            if right_pwm is None:
                message = "If 'left_pwm' is set, 'right_pwm' must be set too."
                raise ValueError(message)
            self.motors.set(
                left_pwm,
                right_pwm,
                self.world_output.header,
                publish=False,
            )
            self.world_output.differential_pwm = self.motors.differential_pwm
        elif right_pwm is not None:
            message = "If 'right_pwm' is set, 'left_pwm' must be set too."
            raise ValueError(message)
        else:
            self.world_output.differential_pwm = None

    def _set_state_reset_flag(self, reset_state: bool | None) -> None:
        if reset_state is not None:
            self.state_reset_flag.set(
                self.world_output.header,
                data=reset_state,
                publish=False,
            )
            self.world_output.state_reset_flag = self.state_reset_flag.boolean
        else:
            self.world_output.state_reset_flag = None

    @property
    def camera(self) -> Camera:
        """Return the front center camera component.

        Returns:
            Camera: The front center camera component.

        """
        return self._camera("front_center")

    @property
    def inertial_measurement_unit(self) -> InertialMeasurementUnit:
        """Return the inertial measurement unit component.

        Returns:
            InertialMeasurementUnit: The inertial measurement unit
            component.

        """
        return self._inertial_measurement_unit("base")

    @property
    def left_wheel_encoder(self) -> WheelEncoder:
        """Return the left wheel encoder component.

        Returns:
            WheelEncoder: The left wheel encoder component.

        """
        return self._wheel_encoder("left")

    @property
    def lights(self) -> Lights:
        """Return the lights component.

        Returns:
            Lights: The lights component.

        """
        return self._lights("base")

    @property
    def motors(self) -> Motors:
        """Return the motors component.

        Returns:
            Motors: The motors component.

        """
        return self._motors("base")

    @property
    def right_wheel_encoder(self) -> WheelEncoder:
        """Return the right wheel encoder component.

        Returns:
            WheelEncoder: The right wheel encoder component.

        """
        return self._wheel_encoder("right")

    def start(self) -> None:
        """Start all the components of the Duckiebot."""
        if not self._gym_mode:
            self.camera.start()
            self.left_wheel_encoder.start()
            self.right_wheel_encoder.start()
            self.time_of_flight_sensor.start()
            self.inertial_measurement_unit.start()
            self.motors.start()
            self.lights.start()
        super().start()

    def step(
        self,
        left_pwm: float | None = None,
        right_pwm: float | None = None,
        front_left_rgba: tuple[float, float, float, float] | None = None,
        front_right_rgba: tuple[float, float, float, float] | None = None,
        back_left_rgba: tuple[float, float, float, float] | None = None,
        back_right_rgba: tuple[float, float, float, float] | None = None,
        *,
        reset_state: bool | None = None,
    ) -> None:
        """Perform a simulation step (gym mode only).

        Args:
            left_pwm (float | None, optional): The PWM signal for the
            left motor. Defaults to `None`.
            right_pwm (float | None, optional): The PWM signal for the
            right motor. Defaults to `None`.
            front_left_rgba (tuple[float, float, float, float] | None, optional): The
            color of the front left light. Defaults to `None`.
            front_right_rgba (tuple[float, float, float, float] | None, optional): The
            color of the front right light. Defaults to `None`.
            back_left_rgba (tuple[float, float, float, float] | None, optional): The
            color of the back left light. Defaults to `None`.
            back_right_rgba (tuple[float, float, float, float] | None, optional): The
            color of the back right light. Defaults to `None`.
            reset_state (bool | None, optional): Whether to reset the
            state. Defaults to `None`.

        Raises:
            RuntimeError: If not in gym mode.

        """
        if not self._gym_mode:
            message = "Step can only be called in gym mode."
            raise RuntimeError(message)
        timestamp = time.time()
        self.world_output.header.timestamp = timestamp
        self._set_differential_pwm(left_pwm, right_pwm)
        self._set_car_lights(
            front_left_rgba,
            front_right_rgba,
            back_left_rgba,
            back_right_rgba,
        )
        self._set_state_reset_flag(reset_state)
        self._world_output.publish(self.world_output)

    def stop(self) -> None:
        """Stop all the components of the Duckiebot."""
        if not self._gym_mode:
            self.camera.stop()
            self.left_wheel_encoder.stop()
            self.right_wheel_encoder.stop()
            self.time_of_flight_sensor.stop()
            self.inertial_measurement_unit.stop()
            self.motors.stop()
            self.lights.stop()
        super().stop()

    @property
    def time_of_flight_sensor(self) -> TimeOfFlightSensor:
        """Return the time-of-flight sensor component.

        Returns:
            TimeOfFlightSensor: The time-of-flight sensor component.

        """
        return self._time_of_flight_sensor("front_center")
