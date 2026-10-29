"""Generic Duckiebot."""

from duckietown.sdk.middleware.base import (
    CameraDriver,
    InertialMeasurementUnit,
    LEDsDriver,
    MotorsDriver,
    PoseDriver,
    ResetFlagDriver,
    TimeOfFlightDriver,
    Twist,
    WheelEncoderDriver,
)
from duckietown.sdk.middleware.dtps.components import (
    DTPSCameraDriver,
    DTPSInertialMeasurementUnit,
    DTPSLEDsDriver,
    DTPSMotorsDriver,
    DTPSPoseDriver,
    DTPSResetFlagDriver,
    DTPSTimeOfFlightDriver,
    DTPSTwist,
    DTPSWheelEncoderDriver,
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

    def _camera(self, name: str) -> CameraDriver:
        return self._get_component(
            "camera",
            name,
            ("robot",),
            CameraDriver,
            DTPSCameraDriver,
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

    def _lights(self, name: str) -> LEDsDriver:
        return self._get_component(
            "lights",
            name,
            ("robot",),
            LEDsDriver,
            LEDsDriver if self._gym_mode else DTPSLEDsDriver,
        )

    def _motors(self, name: str) -> MotorsDriver:
        return self._get_component(
            "motors",
            name,
            ("robot",),
            MotorsDriver,
            MotorsDriver if self._gym_mode else DTPSMotorsDriver,
        )

    def _time_of_flight_sensor(
        self,
        name: str,
    ) -> TimeOfFlightDriver:
        return self._get_component(
            "time_of_flight_sensor",
            name,
            ("robot",),
            TimeOfFlightDriver,
            DTPSTimeOfFlightDriver,
        )

    def _wheel_encoder(self, name: str) -> WheelEncoderDriver:
        return self._get_component(
            "wheel_encoder",
            name,
            ("robot",),
            WheelEncoderDriver,
            DTPSWheelEncoderDriver,
        )

    @property
    def pose(self) -> PoseDriver:
        """Return the pose component.

        Returns:
            Pose: The pose component.

        """
        return self._get_component(
            "pose",
            "",
            ("robot",),
            PoseDriver,
            DTPSPoseDriver,
        )

    @property
    def state_reset_flag(self) -> ResetFlagDriver:
        """Return the state reset flag component.

        Returns:
            StateResetFlag: The state reset flag component.

        """
        return self._get_component(
            "state_reset_flag",
            "",
            ("robot",),
            ResetFlagDriver,
            ResetFlagDriver if self._gym_mode else DTPSResetFlagDriver,
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
