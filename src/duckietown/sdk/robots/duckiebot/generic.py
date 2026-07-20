"""Generic Duckiebot."""

from duckietown.sdk.middleware.components import (
    Camera,
    InertialMeasurementUnit,
    Lights,
    Motors,
    Pose,
    StateResetFlag,
    TimeOfFlightSensor,
    Twist,
    WheelEncoder,
)
from duckietown.sdk.middleware.dtps.components import (
    DTPSCamera,
    DTPSInertialMeasurementUnit,
    DTPSLights,
    DTPSMotors,
    DTPSPose,
    DTPSStateResetFlag,
    DTPSTimeOfFlightSensor,
    DTPSTwist,
    DTPSWheelEncoder,
)
from duckietown.sdk.robots.generic_vehicle import GenericVehicle


class GenericDuckiebot(GenericVehicle):
    """Generic Duckiebot.

    Base class for Duckiebot models. Extends
    :py:class:`GenericVehicle` with differential-drive motors,
    cameras, wheel encoders, IMU, time-of-flight sensor, and
    lights.

    Specific Duckiebot models (e.g. ``DB21M``, ``DB21J``)
    inherit from this class and expose the appropriate subset
    of hardware as named properties.
    """

    def _camera(self, name: str) -> Camera:
        return self._get_component(
            "camera",
            name,
            ("robot",),
            Camera,
            DTPSCamera,
        )

    def _inertial_measurement_unit(
        self,
        name: str,
    ) -> InertialMeasurementUnit:
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

    def start(self) -> None:
        """Start Duckiebot-specific shared components.

        Starts pose, twist, and state-reset-flag components
        when not in gym mode (i.e. for real or non-gym
        simulated robots). Calls :py:meth:`GenericVehicle.start`
        for the common gym/map components.
        """
        if not self._gym_mode:
            self.pose.start()
            self.twist.start()
            self.state_reset_flag.start()
        super().start()

    def stop(self) -> None:
        """Stop Duckiebot-specific shared components.

        Stops pose, twist, and state-reset-flag components
        when not in gym mode. Calls
        :py:meth:`GenericVehicle.stop` for the common
        gym/map components.
        """
        if not self._gym_mode:
            self.pose.stop()
            self.twist.stop()
            self.state_reset_flag.stop()
        super().stop()
