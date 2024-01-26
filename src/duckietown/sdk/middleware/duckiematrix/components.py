import math
import time
from abc import abstractmethod, ABC
from typing import Optional, Any, Tuple, List, Callable, Set

from dt_duckiematrix_protocols.robot import DB21M
from dt_duckiematrix_protocols.robot.features.lights import LED, Lights
from dt_duckiematrix_protocols.robot.features.sensors import SensorAbs

from ..base import GenericSubscriber, GenericPublisher, CameraDriver, TimeOfFlightDriver, \
    WheelEncoderDriver, LEDsDriver, MotorsDriver
from ..duckiematrix import Duckiematrix
from ...types import JPEGImage, BGRImage, PWMSignal, LEDsPattern, RGBAColor, Range

__all__ = [
    "DuckiematrixCameraDriver",
    "DuckiematrixTimeOfFlightDriver",
    "DuckiematrixWheelEncoderDriver",
    "DuckiematrixMotorsDriver",
    "DuckiematrixLEDsDriver"
]

from ...utils.jpeg import JPEG


class GenericDuckiematrixSubscriber(GenericSubscriber, ABC):

    def __init__(self, host: str, robot_name: str):
        super(GenericDuckiematrixSubscriber, self).__init__(host, robot_name)
        # ---
        self._matrix = Duckiematrix.get_instance(self._host)
        self._robot: DB21M = self._matrix.robots.DB21M(self._robot_name)
        self._callbacks: Set[Callable[[Any], None]] = set()

    @property
    @abstractmethod
    def _sensor(self) -> SensorAbs:
        pass

    def _start(self):
        self._sensor.attach(self._callback)

    def _stop(self):
        try:
            self._sensor.detach(self._callback)
        except:
            pass


class GenericDuckiematrixPublisher(GenericPublisher):

    def __init__(self, host: str, robot_name: str, ):
        super(GenericDuckiematrixPublisher, self).__init__(host, robot_name)
        # ---
        self._matrix = Duckiematrix.get_instance(self._host)
        # TODO: this should be a generic robot
        self._robot: DB21M = self._matrix.robots.DB21M(self._robot_name)


class DuckiematrixCameraDriver(CameraDriver, GenericDuckiematrixSubscriber):

    @property
    def _sensor(self) -> SensorAbs:
        return self._robot.camera

    def _unpack(self, msg) -> BGRImage:
        jpeg: JPEGImage = msg.as_uint8()
        return JPEG.decode(jpeg)


class DuckiematrixTimeOfFlightDriver(TimeOfFlightDriver, GenericDuckiematrixSubscriber):

    MAX_RANGE: float = 1.2

    @property
    def _sensor(self) -> SensorAbs:
        # TODO: fix this in the protocols
        # noinspection PyProtectedMember
        return self._robot._time_of_flight

    @staticmethod
    def _unpack(msg) -> Optional[Range]:
        range: float = msg.range
        return None if range >= DuckiematrixTimeOfFlightDriver.MAX_RANGE else range


class DuckiematrixWheelEncoderDriver(WheelEncoderDriver, GenericDuckiematrixSubscriber):

    RESOLUTION: int = 135

    def __init__(self, host: str, robot_name: str, side: str):
        if side not in ["left", "right"]:
            raise ValueError(f"Side '{side}' not recognized. Valid choices are ['left', 'right'].")
        self.side: str = side
        super(DuckiematrixWheelEncoderDriver, self).__init__(host, robot_name)

    @property
    def _sensor(self) -> SensorAbs:
        return getattr(self._robot.wheels, self.side).encoder

    @property
    def resolution(self) -> int:
        return DuckiematrixWheelEncoderDriver.RESOLUTION

    def _unpack(self, msg) -> float:
        ticks: int = msg.ticks
        rotations: float = ticks / self.resolution
        rads: float = rotations * 2 * math.pi
        return rads


class DuckiematrixLEDsDriver(LEDsDriver, GenericDuckiematrixPublisher):

    OFF: RGBAColor = (0, 0, 0, 0)
    IDLE: LEDsPattern = LEDsPattern(
        # white on the front
        front_left=(1, 1, 1, 0.1),
        front_right=(1, 1, 1, 0.1),
        # red on the back
        rear_right=(1, 0, 0, 0.2),
        rear_left=(1, 0, 0, 0.2),
    )

    def publish(self, data: LEDsPattern):
        lights: Lights = self._robot.lights
        colors: List[RGBAColor] = [
            data.front_left, data.rear_left, self.OFF, data.rear_right, data.front_right
        ]
        leds: List[LED] = [
            lights.light0, lights.light1, lights.light2, lights.light3, lights.light4,
        ]
        for led, color in zip(leds, colors):
            self._set_light(led, color)

    @staticmethod
    def _set_light(light: LED, color: RGBAColor):
        light.color.r = int(color[0] * 255.)
        light.color.g = int(color[1] * 255.)
        light.color.b = int(color[2] * 255.)
        light.color.a = int(color[3] * 255.)

    def stop(self):
        self.publish(self.IDLE)
        time.sleep(0.1)
        super(DuckiematrixLEDsDriver, self).stop()

    @staticmethod
    def _pack(data) -> Any:
        pass


class DuckiematrixMotorsDriver(MotorsDriver, GenericDuckiematrixPublisher):

    OFF: float = 0.0

    def publish(self, data: Tuple[PWMSignal, PWMSignal]):
        left, right = data
        self._robot.drive_pwm(left, right)

    def stop(self):
        self.publish((self.OFF, self.OFF))
        time.sleep(0.1)
        super(DuckiematrixMotorsDriver, self).stop()

    @staticmethod
    def _pack(data) -> Any:
        pass
