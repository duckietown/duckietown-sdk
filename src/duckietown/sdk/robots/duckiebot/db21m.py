from duckietown.sdk.middleware.base import \
    WheelEncoderDriver, \
    TimeOfFlightDriver, \
    CameraDriver, \
    MotorsDriver, \
    LEDsDriver

from .generic import GenericDuckiebot


class DB21M(GenericDuckiebot):

    @property
    def camera(self) -> CameraDriver:
        return self._camera("front_center")

    @property
    def range_finder(self) -> TimeOfFlightDriver:
        return self._range_finder("front_center")

    @property
    def left_wheel_encoder(self) -> WheelEncoderDriver:
        return self._wheel_encoder("left")

    @property
    def right_wheel_encoder(self) -> WheelEncoderDriver:
        return self._wheel_encoder("right")

    @property
    def lights(self) -> LEDsDriver:
        return self._lights("base")

    @property
    def motors(self) -> MotorsDriver:
        return self._motors("base")
