"""SDK types and components."""

import logging
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger("duckietown-sdk")

JPEGImage = bytes
BGRImage = np.ndarray
RGB8Color = BGR8Color = tuple[int, int, int]
RGBColor = BGRColor = tuple[float, float, float]
RGBAColor = tuple[float, float, float, float]
PWMSignal = float
Range = float
Ticks = int
ColorName = str
DetectedLines = dict[str, list]
CameraParameters = dict[str, np.ndarray | int]


class AbstractComponent(ABC):
    """Abstract base class for all components.

    Call ``stop()`` explicitly before discarding a running component.
    Finalizers cannot safely wait for transport event loops at exit.
    """

    has_started: bool

    @property
    def is_started(self) -> bool:
        """Return whether the component is running."""
        return self.has_started

    def __init__(self) -> None:
        """Initialize the component."""
        self.has_started = False

    @abstractmethod
    def start(self) -> None:
        """Start the component."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the component."""

    @abstractmethod
    def reset(self) -> None:
        """Reset the component."""


class Component(AbstractComponent):
    """Component."""

    def _start(self) -> None:
        pass

    def _stop(self) -> None:
        pass

    def _reset(self) -> None:
        pass

    def reset(self) -> None:
        """Reset the component."""
        self._reset()

    def start(self) -> None:
        """Start the component.

        Raises:
            RuntimeError: If the component is already started.
            BaseExceptionGroup: If both startup and rollback fail.

        """
        if self.has_started:
            message = "Component already started."
            raise RuntimeError(message)
        try:
            self._start()
        except Exception as startup_error:
            try:
                self._stop()
            except BaseException as cleanup_error:
                self.has_started = True
                message = "Component startup and rollback failed."
                raise BaseExceptionGroup(
                    message,
                    [startup_error, cleanup_error],
                ) from cleanup_error
            self.has_started = False
            raise
        self.has_started = True

    def stop(self) -> None:
        """Stop the component.

        Raises:
            RuntimeError: If the component is not started.

        """
        if not self.has_started:
            message = "Component not started."
            raise RuntimeError(message)
        self._stop()
        self.has_started = False


class CompoundComponent(Component):
    """A compound component that contains other components."""

    _components: dict[tuple[str, str], AbstractComponent]

    def __contains__(
        self,
        component: tuple[str, str | AbstractComponent],
    ) -> bool:
        """Check if the component is in the compound component.

        Args:
            component (tuple[str, str | AbstractComponent]): The
            component to check.

        Raises:
            TypeError: If the component is not a valid type.

        Returns:
            bool: `True` if the component is contained, `False`
            otherwise.

        """
        kind = component[0]
        item = component[1]
        if isinstance(item, str):
            return self.contains(kind, item)
        if isinstance(item, AbstractComponent):
            return item in self._components.values()
        item_class = type(item)
        message = f"Expected 'str' or 'AbstractComponent', got {item_class}."
        raise TypeError(message)

    def __init__(
        self,
        components: dict[tuple[str, str], AbstractComponent] | None = None,
    ) -> None:
        """Initialize the compound component.

        Args:
            components (dict[tuple[str, str], AbstractComponent]): The
            components to include in the compound component.

        """
        super().__init__()
        self._components = components if components is not None else {}

    def _start(self) -> None:
        for component in self._components.values():
            component.start()

    def _stop(self) -> None:
        errors: list[BaseException] = []
        for component in self._components.values():
            if not component.is_started:
                continue
            try:
                component.stop()
            except BaseException as error:
                logger.exception("Failed to stop component %r.", component)
                errors.append(error)
        if errors:
            message = "Failed to stop compound components."
            raise BaseExceptionGroup(message, errors)

    def _reset(self) -> None:
        for component in self._components.values():
            component.reset()

    def add(self, kind: str, name: str, component: AbstractComponent) -> None:
        """Add a component to the compound component.

        Args:
            kind (str): The kind of the component.
            name (str): The name of the component.
            component (AbstractComponent): The component to add.

        """
        self._components[(kind, name)] = component

    def contains(self, kind: str, name: str) -> bool:
        """Check if the compound component contains a component.

        Args:
            kind (str): The kind of the component.
            name (str): The name of the component.

        Returns:
            bool: `True` if the component is contained, `False`
            otherwise.

        """
        return (kind, name) in self._components

    def remove(self, kind: str, name: str) -> None:
        """Remove a component from the compound component.

        Args:
            kind (str): The kind of the component.
            name (str): The name of the component.

        """
        self._components.pop((kind, name), None)


IComponent = AbstractComponent
