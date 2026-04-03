"""Exceptions."""


class PointError(Exception):
    """Point error.

    Raised when a point could not be found.
    """


class TangentVectorError(Exception):
    """Tangent vector error.

    Raised when a tangent vector could not be found.
    """


class TileError(Exception):
    """Tile error.

    Raised when a tile could not be found.
    """
