from typing import Tuple, Optional

from ...middleware.base import TimeOfFlightDriver, CameraDriver, MotorsDriver, WheelEncoderDriver, LEDsDriver, MapLayerDriver
from ...middleware.dtps.components import DTPSCameraDriver, DTPSTimeOfFlightDriver, DTPSWheelEncoderDriver, \
    DTPSMotorsDriver, DTPSLEDsDriver, DTPSMapLayerDriver
from ...types import CompoundComponent


DEFAULT_ROBOT_SWITCHBOARD_PORT: int = 11511
DEFAULT_DUCKIEMATRIX_PORT: int = 7501


class GenericDuckiebot(CompoundComponent):

    def __init__(self, name: str, *, host: Optional[str] = None, simulated: bool = False, port: Optional[int] = None):
        super(GenericDuckiebot, self).__init__()
        self._name: str = name
        self._host: str = host or ("127.0.0.1" if simulated else f"{name}.local")
        self._port: int = port or (DEFAULT_ROBOT_SWITCHBOARD_PORT if not simulated else DEFAULT_DUCKIEMATRIX_PORT)
        self._simulated: bool = simulated

    def _camera(self, name: str) -> CameraDriver:
        key: Tuple[str, str] = ("camera", name)
        if key not in self._components:
            args: dict = {}
            if self._simulated:
                args["path_prefix"] = ("robot",)
            # ---
            self._components[key] = DTPSCameraDriver(self._host, self._port, self._name, name, **args)
        # noinspection PyTypeChecker
        return self._components[key]
    
    def _map_layer(self, name: str) -> MapLayerDriver:
        key: Tuple[str, str] = ("map_layer", name)
        if key not in self._components:
            args: dict = {}
            if self._simulated:
                args["path_prefix"] = ("layer",)
            # ---
            self._components[key] = DTPSMapLayerDriver(self._host, self._port, "", name, **args)
        # noinspection PyTypeChecker
        return self._components[key]

    def _range_finder(self, name: str) -> TimeOfFlightDriver:
        key: Tuple[str, str] = ("range_finder", name)
        if key not in self._components:
            args: dict = {}
            if self._simulated:
                args["path_prefix"] = ("robot",)
            # ---
            self._components[key] = DTPSTimeOfFlightDriver(self._host, self._port, self._name, name, **args)
        # noinspection PyTypeChecker
        return self._components[key]

    def _wheel_encoder(self, name: str) -> WheelEncoderDriver:
        key: Tuple[str, str] = ("wheel_encoder", name)
        if key not in self._components:
            args: dict = {}
            if self._simulated:
                args["path_prefix"] = ("robot",)
            # ---
            self._components[key] = DTPSWheelEncoderDriver(self._host, self._port, self._name, name, **args)
        # noinspection PyTypeChecker
        return self._components[key]

    def _lights(self, name: str) -> LEDsDriver:
        key: Tuple[str, str] = ("lights", name)
        if key not in self._components:
            args: dict = {}
            if self._simulated:
                args["path_prefix"] = ("robot",)
            # ---
            self._components[key] = DTPSLEDsDriver(self._host, self._port, self._name, name, **args)
        # noinspection PyTypeChecker
        return self._components[key]

    def _motors(self, name: str) -> MotorsDriver:
        key: Tuple[str, str] = ("motors", name)
        if key not in self._components:
            args: dict = {}
            if self._simulated:
                args["path_prefix"] = ("robot",)
            # ---
            self._components[key] = DTPSMotorsDriver(self._host, self._port, self._name, name, **args)
        # noinspection PyTypeChecker
        return self._components[key]

    def __repr__(self):
        return (f"GenericDuckiebot(name='{self._name}', host='{self._host}', port='{self._port}', "
                f"simulated={self._simulated})")
