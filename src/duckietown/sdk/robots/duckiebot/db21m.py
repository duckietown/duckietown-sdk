from duckietown.sdk.middleware.base import \
    WheelEncoderDriver, \
    TimeOfFlightDriver, \
    CameraDriver, \
    MotorsDriver, \
    LEDsDriver, \
    MapLayerDriver, \
    DeltaTDriver, \
    ResetFlagDriver

from .generic import GenericDuckiebot


class DB21M(GenericDuckiebot):

    @property
    def camera(self) -> CameraDriver:
        return self._camera("front_center")
    
    @property
    def pose(self) -> CameraDriver:
        return self._pose("pose")
    
    @property
    def delta_t(self) -> DeltaTDriver:
        return self._delta_t("delta_t")
    
    @property
    def map_frames(self) -> MapLayerDriver:
        return self._map_layer("frames")

    @property
    def map_tiles(self) -> MapLayerDriver:
        return self._map_layer("tiles")

    @property
    def map_tile_info(self) -> MapLayerDriver:
        return self._map_layer("tile_maps")


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

    @property
    def reset_flag(self) -> ResetFlagDriver:
        return self._reset_flag("base")
