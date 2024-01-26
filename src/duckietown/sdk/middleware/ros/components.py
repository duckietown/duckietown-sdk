import base64
import math
import time
from abc import ABC
from typing import Optional, Any, Tuple, List

from roslibpy import Message

from .base import ROS, RosTopic
from ..base import GenericSubscriber, GenericPublisher, CameraDriver, TimeOfFlightDriver, \
    WheelEncoderDriver, LEDsDriver, MotorsDriver
from ...types import JPEGImage, BGRImage, PWMSignal, LEDsPattern, RGBAColor, Range

__all__ = [
    "ROSCameraDriver",
    "ROSTimeOfFlightDriver",
    "ROSWheelEncoderDriver",
    "ROSMotorsDriver",
    "ROSLEDsDriver",
    "GenericROSPublisher",
    "GenericROSSubscriber"
]

from ...utils.jpeg import JPEG


class GenericROSSubscriber(GenericSubscriber, ABC):

    def __init__(self, host: str, robot_name: str, topic_name: str, msg_type: str,
                 *,
                 compression=None,
                 latch: bool = False,
                 frequency: float = 0,
                 queue_size: int = 1,
                 queue_length: int = 1,
                 reconnect_on_close: bool = True):
        super(GenericROSSubscriber, self).__init__(host, robot_name)
        # ---
        self._ros = ROS.get_connection(self._host)
        topic_name: str = f"/{self._robot_name}/{topic_name.lstrip('/')}"
        # convert frequency to throttle rate (ms between messages)
        throttle_rate: int = int(1000 * (1.0 / frequency)) if frequency > 0 else 0
        # create underlying topic
        self._topic: RosTopic = RosTopic(
            self._ros,
            topic_name,
            msg_type,
            compression=compression,
            latch=latch,
            throttle_rate=throttle_rate,
            queue_size=queue_size,
            queue_length=queue_length,
            reconnect_on_close=reconnect_on_close
        )

    def _start(self):
        if not self._ros.is_connected:
            self._ros.run()
        # subscribe to topic
        self._topic.subscribe(self._callback)
        # let the parent class start
        super(GenericROSSubscriber, self)._start()

    def _stop(self):
        try:
            self._topic.unsubscribe()
        except:
            pass
        # let the parent class stop
        super(GenericROSSubscriber, self)._stop()


class GenericROSPublisher(GenericPublisher, ABC):

    def __init__(self, host: str, robot_name: str, topic_name: str, msg_type: str):
        super(GenericROSPublisher, self).__init__(host, robot_name)
        # ---
        self._ros = ROS.get_connection(self._host)
        topic_name: str = f"/{self._robot_name}/{topic_name.lstrip('/')}"
        self._topic: RosTopic = RosTopic(self._ros, topic_name, msg_type)
        # data override
        self._override_msg: Optional[dict] = None

    def _start(self):
        # let the parent class start
        super(GenericROSPublisher, self)._start()
        # connect to ROS
        if not self._ros.is_connected:
            self._ros.run()

    def _stop(self):
        # let the parent class stop (important that we do this first)
        super(GenericROSPublisher, self)._stop()
        # unadvertise the topic
        try:
            self._topic.unadvertise()
        except:
            pass

    def _reset(self):
        self._override_msg = None

    def _publish(self, data: Any):
        if not self.is_started:
            return
        # (re)advertise the topic if necessary
        if not self._topic.is_advertised:
            self._topic.advertise()
        # format message
        msg: dict = self._pack(data) if not self._override_msg else self._override_msg
        # publish message
        self._topic.publish(Message(msg))


class ROSCameraDriver(CameraDriver, GenericROSSubscriber):

    def __init__(self, host: str, robot_name: str, **kwargs):
        super(ROSCameraDriver, self).__init__(
            host, robot_name, "/camera_node/image/compressed", "sensor_msgs/CompressedImage", **kwargs
        )

    def _unpack(self, msg) -> BGRImage:
        if self._topic.compression == "cbor":
            jpeg: JPEGImage = msg['data']
        elif self._topic.compression == "none":
            raw: bytes = msg['data'].encode('ascii')
            jpeg: JPEGImage = base64.b64decode(raw)
        else:
            raise ValueError(f"Compression '{self._topic.compression}' not supported")
        # ---
        return JPEG.decode(jpeg)


class ROSTimeOfFlightDriver(TimeOfFlightDriver, GenericROSSubscriber):

    def __init__(self, host: str, robot_name: str, **kwargs):
        super(ROSTimeOfFlightDriver, self).__init__(
            host, robot_name, "/front_center_tof_driver_node/range", "sensor_msgs/Range", **kwargs
        )

    @staticmethod
    def _unpack(msg) -> Optional[Range]:
        max_range: float = msg["max_range"]
        range: float = msg["range"]
        return None if range >= max_range else range


class ROSWheelEncoderDriver(WheelEncoderDriver, GenericROSSubscriber):

    RESOLUTION: int = 135

    def __init__(self, host: str, robot_name: str, side: str, **kwargs):
        if side not in ["left", "right"]:
            raise ValueError(f"Side '{side}' not recognized. Valid choices are ['left', 'right'].")
        super(ROSWheelEncoderDriver, self).__init__(
            host, robot_name, f"/{side}_wheel_encoder_node/tick", "duckietown_msgs/WheelEncoderStamped",
            **kwargs
        )

    @property
    def resolution(self) -> int:
        return ROSWheelEncoderDriver.RESOLUTION

    def _unpack(self, msg) -> float:
        ticks: int = msg["data"]
        rotations: float = ticks / self.resolution
        rads: float = rotations * 2 * math.pi
        return rads


class ROSLEDsDriver(LEDsDriver, GenericROSPublisher):

    OFF: RGBAColor = (0, 0, 0, 0)
    IDLE: LEDsPattern = LEDsPattern(
        # white on the front
        front_left=(1, 1, 1, 0.1),
        front_right=(1, 1, 1, 0.1),
        # red on the back
        rear_right=(1, 0, 0, 0.2),
        rear_left=(1, 0, 0, 0.2),
    )

    def __init__(self, host: str, robot_name: str):
        super(ROSLEDsDriver, self).__init__(
            host, robot_name, "/led_emitter_node/led_pattern", "duckietown_msgs/LEDPattern"
        )

    def publish(self, data: LEDsPattern):
        self._publish(data)

    def _pack(self, data: LEDsPattern) -> dict:
        leds: List[RGBAColor] = [
            # daffy
            data.front_left, data.rear_left, self.OFF, data.rear_right, data.front_right,

            # ente
            # data.front_left, self.OFF, data.front_right, data.rear_right, data.rear_left,
        ]
        return {
            "rgb_vals": [
                dict(zip("rgba", led)) for led in leds
            ]
        }

    def _stop(self):
        self._publish(self.IDLE)
        time.sleep(0.1)
        super(ROSLEDsDriver, self)._stop()


class ROSMotorsDriver(MotorsDriver, GenericROSPublisher):

    OFF: float = 0.0

    def __init__(self, host: str, robot_name: str):
        super(ROSMotorsDriver, self).__init__(
            host, robot_name, "/wheels_driver_node/wheels_cmd", "duckietown_msgs/WheelsCmdStamped"
        )

    def publish(self, data: Tuple[PWMSignal, PWMSignal]):
        self._publish(data)

    def _pack(self, data: Tuple[PWMSignal, PWMSignal]) -> dict:
        return {
            "vel_left": data[0],
            "vel_right": data[1],
        }

    def _stop(self):
        self._override_msg = self._pack((self.OFF, self.OFF))
        # send the 0, 0 command multiple times
        for _ in range(5):
            self._publish((self.OFF, self.OFF))
            time.sleep(1. / 60.)
        # ---
        super(ROSMotorsDriver, self)._stop()
