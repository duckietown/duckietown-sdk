"""Duckietown Postal Service (DTPS) middleware."""

__all__ = ["GenericDTPSPublisher", "GenericDTPSSubscriber"]

import asyncio
import threading
import time
import traceback
from asyncio import CancelledError, Queue
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, ClassVar

from dtps import (
    DTPSContext,
    PublisherInterface,
    SubscriptionInterface,
    context,
)
from dtps_http import RawData
from duckietown_messages.base import BaseMessage

from duckietown.sdk import logger
from duckietown.sdk.middleware.base import GenericPublisher, GenericSubscriber
from duckietown.sdk.middleware.timing_profiler import TimingProfiler

Host = str
Port = int

_DTPS_TIMING_KEY = "__dtps_timing__"


def _get_message_session_id(message: Any) -> int | None:  # noqa: ANN401
    if isinstance(message, dict):
        session_id = message.get("session_id")
    else:
        session_id = getattr(message, "session_id", None)
    return session_id if isinstance(session_id, int) else None


def _attach_dtps_timing_metadata(message: Any, **metadata: int) -> Any:  # noqa: ANN401
    if isinstance(message, BaseMessage):
        native_message: Any = message.to_native()
    else:
        native_message = message
    if not isinstance(native_message, dict):
        return message
    timing = native_message.get(_DTPS_TIMING_KEY)
    timing_dict = dict(timing) if isinstance(timing, dict) else {}
    for key, value in metadata.items():
        if isinstance(value, int):
            timing_dict[key] = value
    if not timing_dict:
        return native_message
    enriched_message = dict(native_message)
    enriched_message[_DTPS_TIMING_KEY] = timing_dict
    return enriched_message


def _get_dtps_timing_metadata(message: Any) -> dict[str, int]:  # noqa: ANN401
    if not isinstance(message, dict):
        return {}
    timing = message.get(_DTPS_TIMING_KEY)
    if not isinstance(timing, dict):
        return {}
    return {
        key: value for key, value in timing.items() if isinstance(value, int)
    }


def _strip_dtps_timing_metadata(message: Any) -> Any:  # noqa: ANN401
    if not isinstance(message, dict) or _DTPS_TIMING_KEY not in message:
        return message
    stripped_message = dict(message)
    stripped_message.pop(_DTPS_TIMING_KEY, None)
    return stripped_message


def _observe_dtps_delta(
    profiler: TimingProfiler,
    key: str,
    end_ns: int,
    start_ns: Any,  # noqa: ANN401
) -> None:
    if not isinstance(start_ns, int):
        return
    profiler.observe(
        key,
        max(0.0, (end_ns - start_ns) / 1_000_000.0),
    )


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
        *,
        shared: bool = True,
    ) -> "DTPSConnector":
        """Get DTPS connector.

        Args:
            host (str): The host address.
            port (int): The port number.
            unix_socket (str | None, optional): The Unix socket path.
            Defaults to `None`.
            shared (bool, optional): Reuse a cached connector. Defaults
            to `True`; private connectors must close their context.

        Returns:
            DTPSConnector: The DTPS connector.

        """
        cls._init()
        if not shared:
            urls = cls._dtps_urls(host, port, unix_socket)
            coroutine = context(urls=urls)
            future = asyncio.run_coroutine_threadsafe(coroutine, cls._loop)
            context_ = future.result()
            return DTPSConnector(context_, cls._loop)
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
    async def _task(coroutine: Coroutine) -> Any:  # noqa: ANN401
        try:
            return await coroutine
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
    _connector_closed: bool
    _endpoint: tuple[str, int]
    _frequency: float | None
    _path_prefix: tuple[str, ...]
    _profiler: TimingProfiler
    _shm_path: str | None
    _shm_only: bool
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
        shm_path: str | None = None,
        shm_only: bool = False,
    ) -> None:
        """Initialize the generic DTPS subscriber."""
        super().__init__(host, robot_name)
        self._endpoint = (host, port)
        self._connector_closed = False
        if shm_only:
            self._connector = DTPS.get_connector(host, port, shared=False)
        else:
            self._connector = DTPS.get_connector(host, port)
        self._frequency = frequency or None
        self._path_prefix = path_prefix
        self._profiler = TimingProfiler(
            "DTPS Subscriber Profiling Information",
        )
        self._shm_path = shm_path
        self._shm_only = shm_only
        self._subscription = None
        self._topic = topic

    def enable_profiling(self, status: bool = True) -> None:  # noqa: FBT001, FBT002
        """Enable or disable DTPS profiling."""
        self._profiler.enable(status=status)

    def print_profiling(self, logger_=logger) -> None:  # noqa: ANN001
        """Log DTPS profiling information."""
        self._profiler.log(logger_)

    def _get_callback(self) -> Callable[[RawData], Awaitable[None]]:
        async def callback(data: RawData) -> None:
            callback_received_at_ns = time.perf_counter_ns()
            with self._profiler.profile("[dtps-subscriber]:deserialize"):
                message = data.get_as_native_object()
            if message is None and self._shm_only:
                return
            timing = _get_dtps_timing_metadata(message)
            _observe_dtps_delta(
                self._profiler,
                "[dtps-subscriber]:engine-send-called-to-receive",
                callback_received_at_ns,
                timing.get("engine_send_called_ns"),
            )
            message = _strip_dtps_timing_metadata(message)
            with self._profiler.profile(
                "[dtps-subscriber]:callback-dispatch",
            ):
                if self._shm_only:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, self._callback, message)
                else:
                    self._callback(message)

        return callback

    async def _subscribe(self) -> None:
        queue = self._connector.context.navigate(
            *self._path_prefix,
            self._robot_name,
            *self._topic,
        )
        callback = self._get_callback()
        if self._shm_path is None:
            self._subscription = await queue.subscribe(
                callback,
                max_frequency=self._frequency,
            )
        else:
            self._subscription = await queue.subscribe(
                callback,
                max_frequency=self._frequency,
                queue_size=1,
                shm_path=self._shm_path,
                shm_only=self._shm_only,
            )

    def _start(self) -> None:
        if self._shm_only and self._connector_closed:
            self._connector = DTPS.get_connector(*self._endpoint, shared=False)
            self._connector_closed = False
        coroutine = self._subscribe()
        self._connector.arun(coroutine, block=self._shm_only)

    def _stop(self) -> None:
        if self._shm_only:
            self._connector.arun(self._stop_shm(), block=True)
            return
        if self._subscription is not None:
            coroutine = self._subscription.unsubscribe()
            self._connector.arun(coroutine, block=True)
            self._subscription = None

    async def _stop_shm(self) -> None:
        try:
            if self._subscription is not None:
                await self._subscription.unsubscribe()
        finally:
            self._subscription = None
            await self._connector.context.aclose()
            self._connector_closed = True


class GenericDTPSPublisher(GenericPublisher):
    """Generic DTPS publisher."""

    _MAX_QUEUE_SIZE = 1
    _connector: DTPSConnector
    _connector_closed: bool
    _endpoint: tuple[str, int]
    _override_message: Any
    _path_prefix: tuple[str, ...]
    _profiler: TimingProfiler
    _queue: Queue
    _publisher_task: asyncio.Task[None] | None
    _shm_path: str | None
    _shm_only: bool
    _topic: tuple[str, ...]

    def __init__(  # noqa: PLR0913
        self,
        host: str,
        port: int,
        robot_name: str,
        topic: tuple[str, ...],
        *,
        path_prefix: tuple[str, ...] = (),
        shm_path: str | None = None,
        shm_only: bool = False,
    ) -> None:
        """Initialize the generic DTPS publisher."""
        GenericPublisher.__init__(self, host, robot_name)
        self._topic = topic
        self._path_prefix = path_prefix
        self._override_message = None
        self._profiler = TimingProfiler(
            "DTPS Publisher Profiling Information",
        )
        self._shm_path = shm_path
        self._shm_only = shm_only
        self._endpoint = (host, port)
        self._connector_closed = False
        self._publisher_task = None
        if shm_only:
            self._connector = DTPS.get_connector(host, port, shared=False)
        else:
            self._connector = DTPS.get_connector(host, port)
        queue = self._connector.arun(self._create_queue(), block=True)
        if queue is None:
            message = "Could not initialize DTPS publisher queue."
            raise RuntimeError(message)
        self._queue = queue
        if not shm_only:
            coroutine = self._publisher()
            self._connector.arun(coroutine)

    def _start(self) -> None:
        if self._shm_only:
            if self._connector_closed:
                self._connector = DTPS.get_connector(
                    *self._endpoint,
                    shared=False,
                )
                self._connector_closed = False
            self._connector.arun(self._start_shm(), block=True)

    async def _start_shm(self) -> None:
        coroutine = DTPSConnector._task(self._publisher())  # noqa: SLF001
        self._publisher_task = asyncio.create_task(coroutine)

    def _stop(self) -> None:
        if self._shm_only:
            self._connector.arun(self._stop_shm(), block=True)

    async def _stop_shm(self) -> None:
        try:
            if self._publisher_task is not None:
                self._publisher_task.cancel()
                await asyncio.gather(
                    self._publisher_task,
                    return_exceptions=True,
                )
                self._publisher_task = None
            while not self._queue.empty():
                self._queue.get_nowait()
                self._queue.task_done()
        finally:
            await self._connector.context.aclose()
            self._connector_closed = True

    def enable_profiling(self, status: bool = True) -> None:  # noqa: FBT001, FBT002
        """Enable or disable DTPS profiling."""
        self._profiler.enable(status=status)

    def print_profiling(self, logger_=logger) -> None:  # noqa: ANN001
        """Log DTPS profiling information."""
        self._profiler.log(logger_)

    @staticmethod
    def _serialize_message(message: Any) -> RawData:  # noqa: ANN401
        if isinstance(message, RawData):
            return message
        if isinstance(message, BaseMessage):
            return message.to_rawdata()
        return RawData.cbor_from_native_object(message)

    async def _create_queue(self) -> Queue:
        return Queue(self._MAX_QUEUE_SIZE)

    async def _publisher(self) -> None:
        queue = self._connector.context.navigate(
            *self._path_prefix,
            self._robot_name,
            *self._topic,
        )
        if self._shm_only:
            await self._publish_pending(queue)
            return
        async with queue.publisher_context() as publisher:
            await self._publish_pending(publisher)

    async def _publish_pending(
        self,
        publisher: DTPSContext | PublisherInterface,
    ) -> None:
        while True:
            raw_data, publish_called_at_ns = await self._queue.get()
            try:
                publish_started_at_ns = time.perf_counter_ns()
                self._profiler.observe(
                    "[dtps-publisher]:publish-called-to-network-start",
                    max(
                        0.0,
                        (publish_started_at_ns - publish_called_at_ns)
                        / 1_000_000.0,
                    ),
                )
                with self._profiler.profile(
                    "[dtps-publisher]:network-publish",
                ):
                    if self._shm_path is None:
                        await publisher.publish(raw_data)
                    else:
                        await publisher.publish(
                            raw_data,
                            shm_path=self._shm_path,
                            shm_only=self._shm_only,
                        )
            finally:
                self._queue.task_done()

    async def _publish_shm(
        self,
        raw_data: RawData,
        publish_called_at_ns: int,
    ) -> None:
        await self._queue.put((raw_data, publish_called_at_ns))
        await self._queue.join()

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
        publish_called_at_ns = time.perf_counter_ns()
        if _get_message_session_id(message) is not None:
            message = _attach_dtps_timing_metadata(
                message,
                host_publish_called_ns=publish_called_at_ns,
            )
        with self._profiler.profile("[dtps-publisher]:serialize"):
            raw_data = self._serialize_message(message)
        # publish message
        if self._shm_only:
            coroutine = self._publish_shm(raw_data, publish_called_at_ns)
        else:
            coroutine = self._queue.put((raw_data, publish_called_at_ns))
        with self._profiler.profile("[dtps-publisher]:schedule-put"):
            self._connector.arun(coroutine, block=self._shm_only)
