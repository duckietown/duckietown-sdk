from duckietown.sdk.middleware.base import WheelEncoderDriver, TimeOfFlightDriver, CameraDriver, MotorsDriver, \
    LEDsDriver

from .generic import GenericDuckiebot


class DB21M(GenericDuckiebot):

    @property
    def camera(self) -> CameraDriver:
        return self._camera

    @property
    def range_finder(self) -> TimeOfFlightDriver:
        return self._range_finder

    @property
    def left_wheel_encoder(self) -> WheelEncoderDriver:
        return self._left_wheel_encoder

    @property
    def right_wheel_encoder(self) -> WheelEncoderDriver:
        return self._right_wheel_encoder

    @property
    def lights(self) -> LEDsDriver:
        return self._lights

    @property
    def motors(self) -> MotorsDriver:
        return self._motors
