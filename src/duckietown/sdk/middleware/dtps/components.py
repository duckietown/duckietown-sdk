import math
import time
from abc import ABC
from asyncio import Queue, QueueFull
from typing import Optional, Any, Tuple, Union

from dtps import DTPSContext, SubscriptionInterface
from dtps_http import RawData
from duckietown_messages.actuators import CarLights, DifferentialPWM
from duckietown_messages.base import BaseMessage
from duckietown_messages.colors import RGBA
from .base import DTPS, DTPSConnector
from ..base import GenericSubscriber, GenericPublisher, CameraDriver, TimeOfFlightDriver, \
    WheelEncoderDriver, LEDsDriver, MotorsDriver, MapLayerDriver
from ...types import JPEGImage, BGRImage, PWMSignal, Range
from ...utils.jpeg import JPEG

__all__ = [
    "DTPSCameraDriver",
    "DTPSTimeOfFlightDriver",
    "DTPSWheelEncoderDriver",
    "DTPSMotorsDriver",
    "DTPSLEDsDriver",
    "DTPSMapLayerDriver",
    "GenericDTPSPublisher",
    "GenericDTPSSubscriber"
]


class GenericDTPSSubscriber(GenericSubscriber, ABC):

    def __init__(self, host: str, port: int, robot_name: str, topic: Tuple[str, ...],
                 *,
                 frequency: float = 0,
                 path_prefix: Optional[Tuple[str, ...]] = None):
        super(GenericDTPSSubscriber, self).__init__(host, robot_name)
        # ---
        self._topic: Tuple[str, ...] = topic
        self._path_prefix: Tuple[str, ...] = path_prefix or tuple()
        self._frequency: Optional[float] = frequency or None
        self._connector: DTPSConnector = DTPS.get_connector(host, port)
        self._subscription: Optional[SubscriptionInterface] = None

    async def _subscribe(self):
        queue: DTPSContext = self._connector.context.navigate(*self._path_prefix, self._robot_name, *self._topic)

        async def cb(data: RawData) -> None:
            self._callback(data.get_as_native_object())

        self._subscription = await queue.subscribe(cb, max_frequency=self._frequency)

    def _start(self):
        # subscribe to topic
        self._connector.arun(self._subscribe())
        # let the parent class start
        super(GenericDTPSSubscriber, self)._start()

    def _stop(self):
        # unsubscribe from topic
        if self._subscription is not None:
            self._connector.arun(self._subscription.unsubscribe())
            self._subscription = None
        # let the parent class stop
        super(GenericDTPSSubscriber, self)._stop()


class GenericDTPSPublisher(GenericPublisher, ABC):

    def __init__(self, host: str, port: int, robot_name: str, topic: Tuple[str, ...],
                 *,
                 path_prefix: Optional[Tuple[str, ...]] = None):
        super(GenericDTPSPublisher, self).__init__(host, robot_name)
        # ---
        self._topic: Tuple[str, ...] = topic
        self._path_prefix: Tuple[str, ...] = path_prefix or tuple()
        self._connector: DTPSConnector = DTPS.get_connector(host, port)
        self._queue: Queue = Queue(maxsize=1)
        # data override
        self._override_msg: Optional[dict] = None
        # start publisher
        self._connector.arun(self._publisher())

    async def _publisher(self):
        queue: DTPSContext = self._connector.context.navigate(*self._path_prefix, self._robot_name, *self._topic)

        async with queue.publisher_context() as publisher:
            while True:
                msg: Union[dict, BaseMessage] = await self._queue.get()
                rd: RawData
                if isinstance(msg, BaseMessage):
                    rd = msg.to_rawdata()
                else:
                    rd = RawData.cbor_from_native_object(msg)
                # ---
                await publisher.publish(rd)

    def _reset(self):
        self._override_msg = None

    def _publish(self, data: Any):
        if not self.is_started:
            #TODO: too silent
            return
        # format message
        msg: dict = self._pack(data) if not self._override_msg else self._override_msg
        # publish message

        #TODO: this should be async all the way
        # self._connector.arun(self._queue.put_nowait(msg))

        try:
            self._queue.put_nowait(msg)
        except QueueFull:
            # print("Queue is full, dropping message.")
            pass


class DTPSCameraDriver(CameraDriver, GenericDTPSSubscriber):

    def __init__(self, host: str, port: int, robot_name: str, sensor_name: str, **kwargs):
        super(DTPSCameraDriver, self).__init__(
            host, port, robot_name, ("sensor", "camera", sensor_name, "jpeg"), **kwargs
        )

    def _unpack(self, msg) -> BGRImage:
        jpeg: JPEGImage = msg['data']
        return JPEG.decode(jpeg)


class DTPSTimeOfFlightDriver(TimeOfFlightDriver, GenericDTPSSubscriber):

    def __init__(self, host: str, port: int, robot_name: str, sensor_name: str, **kwargs):
        super(DTPSTimeOfFlightDriver, self).__init__(
            host, port, robot_name, ("sensor", "time_of_flight", sensor_name, "range"), **kwargs
        )

    @staticmethod
    def _unpack(msg) -> Optional[Range]:
        range_m: float = msg["data"]
        return range_m


class DTPSWheelEncoderDriver(WheelEncoderDriver, GenericDTPSSubscriber):
    RESOLUTION: int = 135

    def __init__(self, host: str, port: int, robot_name: str, sensor_name: str, **kwargs):
        if sensor_name not in ["left", "right"]:
            raise ValueError(f"Side '{sensor_name}' not recognized. Valid choices are ['left', 'right'].")
        super(DTPSWheelEncoderDriver, self).__init__(
            host, port, robot_name, ("sensor", "wheel_encoder", sensor_name, "ticks"), **kwargs
        )

    @property
    def resolution(self) -> int:
        return DTPSWheelEncoderDriver.RESOLUTION

    def _unpack(self, msg) -> float:
        ticks: int = msg["data"]
        rotations: float = ticks / self.resolution
        rads: float = rotations * 2 * math.pi
        return rads
    

class DTPSMapLayerDriver(MapLayerDriver, GenericDTPSSubscriber):
    def __init__(self, host: str, port: int, robot_name: str, sensor_name: str, **kwargs):
        super(DTPSMapLayerDriver, self).__init__(
            host, port, robot_name, ("sensor", "map", sensor_name, "map"), **kwargs
        )

    def _unpack(self, msg) -> dict:
        return msg["data"]

class DTPSLEDsDriver(LEDsDriver, GenericDTPSPublisher):
    OFF: RGBA = RGBA(r=0, g=0, b=0, a=0)
    IDLE: CarLights = CarLights(
        # white on the front
        front_left=RGBA(r=1, g=1, b=1, a=0.1),
        front_right=RGBA(r=1, g=1, b=1, a=0.1),
        # red on the back
        back_right=RGBA(r=1, g=0, b=0, a=0.2),
        back_left=RGBA(r=1, g=0, b=0, a=0.2),
    )

    def __init__(self, host: str, port: int, robot_name: str, actuator_name: str, **kwargs):
        super(DTPSLEDsDriver, self).__init__(
            host, port, robot_name, ("actuator", "lights", actuator_name, "pattern"), **kwargs
        )

    def publish(self, data: CarLights):
        self._publish(data)

    def _pack(self, data: CarLights) -> BaseMessage:
        return data

    def _stop(self):
        self._publish(self.IDLE)
        time.sleep(0.1)
        super(DTPSLEDsDriver, self)._stop()


class DTPSMotorsDriver(MotorsDriver, GenericDTPSPublisher):
    OFF: float = 0.0

    def __init__(self, host: str, port: int, robot_name: str, actuator_name: str, **kwargs):
        super(DTPSMotorsDriver, self).__init__(
            host, port, robot_name, ("actuator", "wheels", actuator_name, "pwm"), **kwargs
        )

    def publish(self, data: Tuple[PWMSignal, PWMSignal]):
        self._publish(data)

    def _pack(self, data: Tuple[PWMSignal, PWMSignal]) -> DifferentialPWM:
        return DifferentialPWM(left=data[0], right=data[1])

    def _stop(self):
        self._override_msg = self._pack((self.OFF, self.OFF))
        # send the 0, 0 command multiple times
        for _ in range(5):
            self._publish((self.OFF, self.OFF))
            time.sleep(1. / 60.)
        # ---
        super(DTPSMotorsDriver, self)._stop()
