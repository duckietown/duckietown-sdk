"""Duckietown SDK middleware."""

__all__ = ["GenericPublisher", "GenericSubscriber"]

from abc import abstractmethod
from collections.abc import Callable
from threading import Event
from typing import Any, Generic, TypeVar

from duckietown.sdk.components import Component

T = TypeVar("T")


class GenericNetworkComponent(Component):
    """Generic network component."""

    _host: str
    _path_prefix: str | tuple[str, ...]
    _robot_name: str

    def __init__(
        self,
        host: str,
        robot_name: str,
        path_prefix: str = "",
        **_: Any,
    ) -> None:
        """Initialize the generic network component.

        Args:
            host (str): The host address of the component.
            robot_name (str): The name of the robot.
            path_prefix (str, optional): The path prefix for the
            component. Defaults to `""`.
            **_: Additional keyword arguments.

        """
        super().__init__()
        self._host = host
        self._robot_name = robot_name
        self._path_prefix = path_prefix


class GenericPublisher(GenericNetworkComponent):
    """Generic publisher."""

    @abstractmethod
    def publish(self, data: Any) -> None:
        """Publish data.

        Args:
            data (Any): The data to publish.

        Raises:
            ValueError: If the data is invalid.

        """


class GenericSubscriber(GenericNetworkComponent, Generic[T]):
    """Generic subscriber."""

    _callbacks: set[Callable[[Any], None]]
    _event: Event
    _reading: T | None
    _reading_used: bool

    def __init__(
        self,
        host: str,
        robot_name: str,
        path_prefix: str = "",
        **kwargs: Any,
    ) -> None:
        """Initialize the generic subscriber.

        Args:
            host (str): The host address of the component.
            robot_name (str): The name of the robot.
            path_prefix (str, optional): The path prefix for the
            component. Defaults to `""`.
            **kwargs: Additional keyword arguments.

        """
        super().__init__(
            host=host,
            robot_name=robot_name,
            path_prefix=path_prefix,
            **kwargs,
        )
        # async behavior
        self._callbacks = set()
        # sync behavior
        self._reading = None
        self._reading_used = False
        self._event = Event()

    def _callback(self, message: Any) -> None:
        data = self._unpack(message)
        # notify sync readers
        self._reading = data
        self._reading_used = False
        self._event.set()
        # perform async callbacks
        for callback in self._callbacks:
            callback(data)

    def _grab_current(self) -> T | None:
        if self._reading_used:
            return None
        self._reading_used = True
        return self._reading

    @abstractmethod
    def _unpack(self, message: Any) -> Any:
        pass

    def attach(self, callback: Callable[[Any], None]) -> None:
        """Attach a callback to the subscriber.

        Args:
            callback (Callable[[Any], None]): The callback to attach.

        """
        self._callbacks.add(callback)

    def detach(self, callback: Callable[[Any], None]) -> None:
        """Detach a callback from the subscriber.

        Args:
            callback (Callable[[Any], None]): The callback to detach.

        """
        self._callbacks.remove(callback)

    @property
    def latest(self) -> T | None:
        """Get the latest reading.

        Returns:
            T | None: The latest reading or `None` if not available.

        """
        return self._reading

    def get(
        self,
        *,
        block: bool = False,
        clean_up: bool = False,
        timeout: float | None = None,
    ) -> T | None:
        """Get the latest reading.

        If the subscriber has not been started, this method will
        automatically start it before attempting to get a reading.

        Args:
            block (bool, optional): Whether to block until a reading is
            available. Defaults to `False`.
            clean_up (bool, optional): Whether to stop the
            subscriber after getting the reading. Defaults to `False`.
            timeout (float | None, optional): The timeout for blocking
            behavior. Defaults to `None`.

        Returns:
            T | None: The latest reading or `None` if not available.

        """
        if not self.has_started:
            self.start()
        if block:
            if not self._event.wait(timeout):
                return None
            self._event.clear()
        data = self._grab_current()
        if clean_up:
            self.stop()
        return data
