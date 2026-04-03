"""Duckietown Postal Service (DTPS) middleware."""

__all__ = ["GenericDTPSPublisher", "GenericDTPSSubscriber"]

import asyncio
import threading
import traceback
from asyncio import CancelledError, Queue
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, ClassVar

from dtps import DTPSContext, SubscriptionInterface, context
from dtps_http import RawData
from duckietown_messages.base import BaseMessage

from duckietown.sdk import logger
from duckietown.sdk.middleware.base import GenericPublisher, GenericSubscriber

Host = str
Port = int


class DTPS:
    """Duckietown Postal Service (DTPS) class."""

    _connectors: ClassVar[dict[tuple[Host, Port], "DTPSConnector"]] = {}
    _contexts: ClassVar[dict[tuple[Host, Port], DTPSContext]] = {}
    _loop: ClassVar[asyncio.AbstractEventLoop] = asyncio.new_event_loop()
    _worker: ClassVar[threading.Thread | None] = None

    @staticmethod
    def _dtps_urls(
        host: str,
        port: int,
        unix_socket: str | None = None,
    ) -> list[str]:
        urls = [f"http://{host}:{port}/"]
        if unix_socket is not None:
            encoded = unix_socket.replace("/", "%2F")
            urls.append(f"http+unix://{encoded}/")
        return urls

    @classmethod
    async def _get_context(
        cls,
        host: str,
        port: int,
        unix_socket: str | None = None,
    ) -> DTPSContext:
        cls._init()
        if (host, port) in cls._contexts:
            return cls._contexts[(host, port)]
        urls = cls._dtps_urls(host, port, unix_socket)
        context_ = await context(urls=urls)
        cls._contexts[(host, port)] = context_
        return context_

    @classmethod
    def _get_start_background_loop(
        cls,
    ) -> Callable[[asyncio.AbstractEventLoop], None]:
        def start_background_loop(loop: asyncio.AbstractEventLoop) -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        return start_background_loop

    @classmethod
    def _init(cls) -> None:
        if cls._worker is None:
            start_background_loop = cls._get_start_background_loop()
            cls._worker = threading.Thread(
                target=start_background_loop,
                args=(cls._loop,),
                daemon=True,
            )
            cls._worker.start()

    @classmethod
    def get_connector(
        cls,
        host: str,
        port: int,
        unix_socket: str | None = None,
    ) -> "DTPSConnector":
        """Get DTPS connector.

        Args:
            host (str): The host address.
            port (int): The port number.
            unix_socket (str | None, optional): The Unix socket path.
            Defaults to `None`.

        Returns:
            DTPSConnector: The DTPS connector.

        """
        cls._init()
        # create a new connector if it doesn't exist
        if (host, port) not in cls._connectors:
            coroutine = cls._get_context(host, port, unix_socket)
            future = asyncio.run_coroutine_threadsafe(coroutine, cls._loop)
            context_ = future.result()
            cls._connectors[(host, port)] = DTPSConnector(context_, cls._loop)
        return cls._connectors[(host, port)]


class DTPSConnector:
    """DTPS connector."""

    _context: DTPSContext
    _loop: asyncio.AbstractEventLoop

    def __init__(
        self,
        context_: DTPSContext,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Initialize the DTPS connector."""
        self._context = context_
        self._loop = loop

    @staticmethod
    async def _task(coroutine: Coroutine) -> None:
        try:
            await coroutine
        except Exception:  # noqa: BLE001
            logger.error(f"Error in task: {coroutine.__name__}")
            traceback.print_exc()

    def arun(self, coroutine: Coroutine, *, block: bool = False) -> Any:  # noqa: ANN401
        """Run a coroutine in the DTPS event loop.

        Args:
            coroutine (Coroutine): The coroutine to run.
            block (bool, optional): Whether to block until the coroutine
            is done. Defaults to `False`.

        Returns:
            Any: The result of the coroutine, if awaited.

        """
        coroutine = self._task(coroutine)
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        if block:
            try:
                return future.result()
            except (CancelledError, TimeoutError, Exception) as error:  # noqa: BLE001
                logger.error(
                    f"Error occurred while running coroutine: {error}",
                )
        return None

    @property
    def context(self) -> DTPSContext:
        """Get the DTPS context.

        Returns:
            DTPSContext: The DTPS context.

        """
        return self._context


class GenericDTPSSubscriber(GenericSubscriber):
    """Generic DTPS subscriber."""

    _connector: DTPSConnector
    _frequency: float | None
    _path_prefix: tuple[str, ...]
    _subscription: SubscriptionInterface | None
    _topic: tuple[str, ...]

    def __init__(  # noqa: PLR0913
        self,
        host: str,
        port: int,
        robot_name: str,
        topic: tuple[str, ...],
        *,
        frequency: float = 0,
        path_prefix: tuple[str, ...] = (),
    ) -> None:
        """Initialize the generic DTPS subscriber."""
        super().__init__(host, robot_name)
        self._connector = DTPS.get_connector(host, port)
        self._frequency = frequency or None
        self._path_prefix = path_prefix
        self._subscription = None
        self._topic = topic

    def _get_callback(self) -> Callable[[RawData], Awaitable[None]]:
        async def callback(data: RawData) -> None:
            message = data.get_as_native_object()
            self._callback(message)

        return callback

    async def _subscribe(self) -> None:
        queue = self._connector.context.navigate(
            *self._path_prefix,
            self._robot_name,
            *self._topic,
        )
        callback = self._get_callback()
        self._subscription = await queue.subscribe(
            callback,
            max_frequency=self._frequency,
        )

    def _start(self) -> None:
        coroutine = self._subscribe()
        self._connector.arun(coroutine)

    def _stop(self) -> None:
        if self._subscription is not None:
            coroutine = self._subscription.unsubscribe()
            self._connector.arun(coroutine)
            self._subscription = None


class GenericDTPSPublisher(GenericPublisher):
    """Generic DTPS publisher."""

    _MAX_QUEUE_SIZE = 1
    _connector: DTPSConnector
    _override_message: Any
    _path_prefix: tuple[str, ...]
    _queue: Queue
    _topic: tuple[str, ...]

    def __init__(
        self,
        host: str,
        port: int,
        robot_name: str,
        topic: tuple[str, ...],
        *,
        path_prefix: tuple[str, ...] = (),
    ) -> None:
        """Initialize the generic DTPS publisher."""
        super().__init__(host, robot_name)
        self._topic = topic
        self._path_prefix = path_prefix
        self._override_message = None
        self._queue = Queue(self._MAX_QUEUE_SIZE)
        self._connector = DTPS.get_connector(host, port)
        coroutine = self._publisher()
        self._connector.arun(coroutine)

    async def _publisher(self) -> None:
        queue = self._connector.context.navigate(
            *self._path_prefix,
            self._robot_name,
            *self._topic,
        )
        async with queue.publisher_context() as publisher:
            while True:
                message = await self._queue.get()
                if isinstance(message, BaseMessage):
                    raw_data = message.to_rawdata()
                else:
                    raw_data = RawData.cbor_from_native_object(message)
                await publisher.publish(raw_data)

    def publish(self, data: Any) -> None:  # noqa: ANN401
        """Publish data.

        Args:
            data (Any): The data to publish.

        Raises:
            RuntimeError: If the component is not started.

        """
        if not self.has_started:
            message = "Component not started. Cannot publish data."
            raise RuntimeError(message)
        # format message
        message = (
            data if not self._override_message else self._override_message
        )
        # publish message
        coroutine = self._queue.put(message)
        self._connector.arun(coroutine)
