from abc import abstractmethod
from typing import Tuple, Dict, Union

import numpy as np

JPEGImage = bytes
BGRImage = np.ndarray
RGB8Color = BGR8Color = Tuple[int, int, int]
RGBColor = BGRColor = Tuple[float, float, float]
RGBAColor = Tuple[float, float, float, float]
PWMSignal = float
Range = float
Ticks = int
ColorName = str
DetectedLines = Dict[str, list]
CameraParameters = Dict[str, Union[np.ndarray, int]]


class IComponent:

    @property
    @abstractmethod
    def is_started(self) -> bool:
        pass

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def reset(self):
        pass

    def __del__(self):
        if self.is_started:
            try:
                self.stop()
            except:
                pass


class Component(IComponent):

    def __init__(self):
        self._is_started: bool = False

    @property
    def is_started(self) -> bool:
        return self._is_started

    def _start(self):
        pass

    def _stop(self):
        pass

    def _reset(self):
        pass

    def start(self):
        if self._is_started:
            raise RuntimeError("Component already started.")
        # ---
        self._start()
        self._is_started = True

    def stop(self):
        if not self._is_started:
            raise RuntimeError("Component not started.")
        # ---
        self._stop()
        self._is_started = False

    def reset(self):
        if self._is_started:
            raise RuntimeError("You cannot reset a component while it is running.")
        # ---
        self._reset()
        self._is_started = False


class CompoundComponent(Component):

    def __init__(self, components: Dict[str, IComponent] = None):
        super(CompoundComponent, self).__init__()
        self._components: Dict[Tuple[str, str], IComponent] = components or {}

    def add(self, kind: str, name: str, component: IComponent):
        self._components[(kind, name)] = component

    def remove(self, kind: str, name: str):
        self._components.pop((kind, name), None)

    def contains(self, kind: str, name: str):
        return (kind, name) in self._components

    def __contains__(self, kind: str, item):
        if isinstance(item, str):
            return self.contains(kind, item)
        elif isinstance(item, IComponent):
            # TODO: this looks wrong
            return self._components.values().__contains__(kind, item)
        else:
            return super(CompoundComponent, self).__contains__(kind, item)

    def _start(self):
        for component in self._components.values():
            component.start()

    def _stop(self):
        for component in self._components.values():
            component.stop()

    def _reset(self):
        for component in self._components.values():
            component.reset()
