from abc import abstractmethod, ABC
from threading import Event
from typing import Any, Callable, Set, TypeVar, Generic, Optional

from ..types import Component, PWMSignal, LEDsPattern

Msg = Any

T = TypeVar('T')


class GenericNetworkComponent(Component, ABC):

    def __init__(self, host: str, robot_name: str):
        super(GenericNetworkComponent, self).__init__()
        self._robot_name: str = robot_name
        self._host: str = host


class GenericSubscriber(GenericNetworkComponent, Generic[T], ABC):

    def __init__(self, host: str, robot_name: str):
        super(GenericSubscriber, self).__init__(host, robot_name)
        # ---
        # async behavior
        self._callbacks: Set[Callable[[Any], None]] = set()
        # sync behavior
        self._reading: T = None
        self._reading_used: bool = False
        self._event: Event = Event()

    def attach(self, callback: Callable[[Any], None]):
        self._callbacks.add(callback)

    def detach(self, callback: Callable[[Any], None]):
        self._callbacks.remove(callback)

    @property
    def latest(self) -> Optional[T]:
        return self._reading

    def _grab_current(self) -> Optional[T]:
        if self._reading_used:
            return None
        self._reading_used = True
        return self._reading

    def capture(self, block: bool = False, timeout: Optional[float] = None) -> Optional[T]:
        if not self._is_started:
            raise RuntimeError("Component is not started.")
        # blocking behavior
        if block:
            has_timed_out: bool = not self._event.wait(timeout)
            if has_timed_out:
                return None
            self._event.clear()
        return self._grab_current()

    def _callback(self, msg):
        data: Any = self._unpack(msg)
        # notify sync readers
        self._reading = data
        self._reading_used = False
        self._event.set()
        # perform async callbacks
        for callback in self._callbacks:
            callback(data)

    @staticmethod
    @abstractmethod
    def _unpack(msg) -> Any:
        pass


class GenericPublisher(GenericNetworkComponent, ABC):

    @staticmethod
    @abstractmethod
    def _pack(data) -> Msg:
        pass

    @abstractmethod
    def publish(self, data: Any):
        pass


class CameraDriver(GenericSubscriber, ABC):
    pass


class TimeOfFlightDriver(GenericSubscriber, ABC):
    pass


class WheelEncoderDriver(GenericSubscriber, ABC):
    pass


class LEDsDriver(GenericPublisher, ABC):

    def set(self, pattern: LEDsPattern):
        self.publish(pattern)


class MotorsDriver(GenericPublisher, ABC):

    def set_pwm(self, left: PWMSignal, right: PWMSignal):
        self.publish((left, right))
