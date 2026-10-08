"""DB21M Duckiebot."""

from duckietown_messages.actuators import CarLights, DifferentialPWM
from duckietown_messages.colors.rgba import RGBA
from duckietown_messages.simulation import WorldEntityOutput
from duckietown_messages.standard import Boolean, Header

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

    @staticmethod
    def _make_rgba(
        header: Header,
        rgba: tuple[float, float, float, float],
    ) -> RGBA:
        return RGBA(
            header=header,
            r=rgba[0],
            g=rgba[1],
            b=rgba[2],
            a=rgba[3],
        )

    def _set_car_lights(
        self,
        header: Header,
        front_left_rgba: tuple[float, float, float, float] | None,
        front_right_rgba: tuple[float, float, float, float] | None,
        back_left_rgba: tuple[float, float, float, float] | None,
        back_right_rgba: tuple[float, float, float, float] | None,
    ) -> object | None:
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
            return CarLights(
                header=header,
                front_left=self._make_rgba(header, front_left_rgba),
                front_right=self._make_rgba(header, front_right_rgba),
                back_left=self._make_rgba(header, back_left_rgba),
                back_right=self._make_rgba(header, back_right_rgba),
            )
        return None

    def _set_differential_pwm(
        self,
        header: Header,
        left_pwm: float | None,
        right_pwm: float | None,
    ) -> object | None:
        if left_pwm is not None:
            if right_pwm is None:
                message = "If 'left_pwm' is set, 'right_pwm' must be set too."
                raise ValueError(message)
            return DifferentialPWM(
                header=header,
                left=left_pwm,
                right=right_pwm,
            )
        if right_pwm is not None:
            message = "If 'right_pwm' is set, 'left_pwm' must be set too."
            raise ValueError(message)
        return None

    def _set_state_reset_flag(
        self,
        header: Header,
        reset_state: bool | None,
    ) -> object | None:
        if reset_state is not None:
            return Boolean(
                header=header,
                data=reset_state,
            )
        return None

    def make_world_entity_output(  # noqa: PLR0913
        self,
        left_pwm: float | None = None,
        right_pwm: float | None = None,
        front_left_rgba: tuple[float, float, float, float] | None = None,
        front_right_rgba: tuple[float, float, float, float] | None = None,
        back_left_rgba: tuple[float, float, float, float] | None = None,
        back_right_rgba: tuple[float, float, float, float] | None = None,
        *,
        reset_state: bool | None = None,
    ) -> WorldEntityOutput:
        """Build the per-entity gym actuator payload for this Duckiebot."""
        header = Header()
        differential_pwm = self._set_differential_pwm(
            header,
            left_pwm,
            right_pwm,
        )
        car_lights = self._set_car_lights(
            header,
            front_left_rgba,
            front_right_rgba,
            back_left_rgba,
            back_right_rgba,
        )
        state_reset_flag = self._set_state_reset_flag(
            header,
            reset_state,
        )
        return WorldEntityOutput(
            differential_pwm=differential_pwm,
            car_lights=car_lights,
            state_reset_flag=state_reset_flag,
        )

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
