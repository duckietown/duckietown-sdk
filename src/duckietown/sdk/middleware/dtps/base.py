import asyncio
import threading
import traceback
from asyncio import Future
from typing import Dict, Tuple, Optional, Any, Coroutine, List

from dtps import DTPSContext, context

Host = str
Port = int


class DTPS:
    _loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    _worker: threading.Thread = None
    _contexts: Dict[Tuple[Host, Port], DTPSContext] = {}
    _connectors: Dict[Tuple[Host, Port], 'DTPSConnector'] = {}

    @classmethod
    def _init(cls):
        if cls._worker is None:
            def start_background_loop(_loop: asyncio.AbstractEventLoop) -> None:
                asyncio.set_event_loop(_loop)
                _loop.run_forever()

            cls._worker = threading.Thread(target=start_background_loop, args=(cls._loop,), daemon=True)
            cls._worker.start()

    @classmethod
    async def get_context(cls, host: str, port: int, unix_socket: Optional[str] = None) -> DTPSContext:
        cls._init()
        if (host, port) in cls._contexts:
            return cls._contexts[(host, port)]
        cxt: DTPSContext = await context(urls=cls._dtps_urls(host, port, unix_socket))
        cls._contexts[(host, port)] = cxt
        return cxt

    @classmethod
    def get_connector(cls, host: str, port: int, unix_socket: Optional[str] = None) -> 'DTPSConnector':
        cls._init()
        # create a new connector if it doesn't exist
        if (host, port) not in cls._connectors:
            cxt: DTPSContext = asyncio.run_coroutine_threadsafe(
                cls.get_context(host, port, unix_socket), cls._loop).result()
            cls._connectors[(host, port)] = DTPSConnector(cls._loop, cxt)
        # ---
        return cls._connectors[(host, port)]

    @staticmethod
    def _dtps_urls(host: str, port: int, unix_socket: Optional[str] = None) -> List[str]:
        urls: List[str] = [f"http://{host}:{port}/"]
        if unix_socket is not None:
            urls.append(f"http+unix://[{unix_socket}]/")
        # ---
        return urls


class DTPSConnector:

    def __init__(self, loop: asyncio.AbstractEventLoop, cxt: DTPSContext):
        self._loop: asyncio.AbstractEventLoop = loop
        self._context: DTPSContext = cxt

    @property
    def context(self) -> DTPSContext:
        return self._context

    def arun(self, coro: Coroutine, block: bool = False) -> Optional[Any]:
        future: Future = asyncio.run_coroutine_threadsafe(self._task(coro), self._loop)
        if block:
            return future.result()

    @staticmethod
    async def _task(coro: Coroutine):
        # noinspection PyBroadException
        try:
            await coro
        except Exception:
            print(f"Exception in task: {coro.__name__}")
            traceback.print_exc()
