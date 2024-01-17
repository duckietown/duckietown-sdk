from ...middleware.base import TimeOfFlightDriver, CameraDriver, MotorsDriver, WheelEncoderDriver, LEDsDriver
from ...middleware.duckiematrix.components import DuckiematrixCameraDriver, DuckiematrixTimeOfFlightDriver, \
    DuckiematrixWheelEncoderDriver, DuckiematrixMotorsDriver, DuckiematrixLEDsDriver
from ...middleware.ros.components import ROSCameraDriver, ROSTimeOfFlightDriver, ROSWheelEncoderDriver, \
    ROSMotorsDriver, ROSLEDsDriver
from ...types import CompoundComponent


class GenericDuckiebot(CompoundComponent):

    def __init__(self, name: str, *, host: str = None, simulated: bool = False):
        super(GenericDuckiebot, self).__init__()
        self._name: str = name
        self._host: str = host or ("127.0.0.1" if simulated else f"{name}.local")
        self._simulated: bool = simulated

    @property
    def _camera(self) -> CameraDriver:
        if "camera" not in self._components:
            if self._simulated:
                self._components["camera"] = DuckiematrixCameraDriver(self._host, self._name)
            else:
                self._components["camera"] = ROSCameraDriver(self._host, self._name)
        # noinspection PyTypeChecker
        return self._components["camera"]

    @property
    def _range_finder(self) -> TimeOfFlightDriver:
        if "range_finder" not in self._components:
            if self._simulated:
                self._components["range_finder"] = DuckiematrixTimeOfFlightDriver(self._host, self._name)
            else:
                self._components["range_finder"] = ROSTimeOfFlightDriver(self._host, self._name)
        # noinspection PyTypeChecker
        return self._components["range_finder"]

    @property
    def _left_wheel_encoder(self) -> WheelEncoderDriver:
        if "left_wheel_encoder" not in self._components:
            if self._simulated:
                self._components["left_wheel_encoder"] = DuckiematrixWheelEncoderDriver(
                    self._host, self._name, "left")
            else:
                self._components["left_wheel_encoder"] = ROSWheelEncoderDriver(
                    self._host, self._name, "left")
        # noinspection PyTypeChecker
        return self._components["left_wheel_encoder"]

    @property
    def _right_wheel_encoder(self) -> WheelEncoderDriver:
        if "right_wheel_encoder" not in self._components:
            if self._simulated:
                self._components["right_wheel_encoder"] = DuckiematrixWheelEncoderDriver(
                    self._host, self._name, "right")
            else:
                self._components["right_wheel_encoder"] = ROSWheelEncoderDriver(
                    self._host, self._name, "right")
        # noinspection PyTypeChecker
        return self._components["right_wheel_encoder"]

    @property
    def _lights(self) -> LEDsDriver:
        if "lights" not in self._components:
            if self._simulated:
                self._components["lights"] = DuckiematrixLEDsDriver(self._host, self._name)
            else:
                self._components["lights"] = ROSLEDsDriver(self._host, self._name)
        # noinspection PyTypeChecker
        return self._components["lights"]

    @property
    def _motors(self) -> MotorsDriver:
        if "motors" not in self._components:
            if self._simulated:
                self._components["motors"] = DuckiematrixMotorsDriver(self._host, self._name)
            else:
                self._components["motors"] = ROSMotorsDriver(self._host, self._name)
        # noinspection PyTypeChecker
        return self._components["motors"]

    def __repr__(self):
        return f"GenericDuckiebot(name='{self._name}', host='{self._host}', simulated={self._simulated})"
