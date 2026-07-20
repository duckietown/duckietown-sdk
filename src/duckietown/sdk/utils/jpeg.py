"""JPEG utilities."""

import io
import sys
from abc import ABC, abstractmethod

import numpy as np


class AbstractJPEG(ABC):
    """Abstract base class for JPEG encoding and decoding."""

    @classmethod
    @abstractmethod
    def encode(cls, image: np.ndarray) -> bytes:
        """Encode a BGR image to JPEG format.

        Args:
            image (np.ndarray): The BGR image to encode.

        Returns:
            bytes: The encoded JPEG image.

        """

    @classmethod
    @abstractmethod
    def decode(cls, data: bytes) -> np.ndarray:
        """Decode a JPEG image to BGR format.

        Args:
            data (bytes): The encoded JPEG image.

        Raises:
            RuntimeError: If decoding fails or the image format is
            unsupported.

        Returns:
            np.ndarray: The decoded BGR image.

        """


if sys.platform == "linux":
    import turbojpeg

    jpeg = turbojpeg.TurboJPEG()

    class JPEG(AbstractJPEG):
        """JPEG encoding and decoding."""

        @classmethod
        def encode(cls, bgr_image: np.ndarray) -> bytes:
            """Encode a BGR image to JPEG format.

            Args:
                bgr_image (np.ndarray): The BGR image to encode.

            Returns:
                bytes: The encoded JPEG image.

            """
            return jpeg.encode(bgr_image)

        @classmethod
        def decode(cls, data: bytes) -> np.ndarray:
            """Decode a JPEG image to BGR format.

            Args:
                data (bytes): The encoded JPEG image.

            Returns:
                np.ndarray: The decoded BGR image.

            """
            return jpeg.decode(data)

elif sys.platform == "darwin":
    from PIL import Image

    class JPEG(AbstractJPEG):
        """JPEG encoding and decoding."""

        @classmethod
        def encode(cls, bgr_image: np.ndarray) -> bytes:
            """Encode a BGR image to JPEG format.

            Args:
                bgr_image (np.ndarray): The BGR image to encode.

            Returns:
                bytes: The encoded JPEG image.

            """
            buffer = io.BytesIO()
            rgb_image = bgr_image[..., ::-1]
            image = Image.fromarray(rgb_image)
            image.save(buffer, format="JPEG")
            return buffer.getvalue()

        @classmethod
        def decode(cls, data: bytes) -> np.ndarray:
            """Decode a JPEG image to BGR format.

            Args:
                data (bytes): The encoded JPEG image.

            Returns:
                np.ndarray: The decoded BGR image.

            """
            buffer = io.BytesIO(data)
            image = Image.open(buffer)
            rgb_image = np.array(image)
            return rgb_image[..., ::-1]

else:

    class JPEG(AbstractJPEG):
        """JPEG encoding and decoding."""

        @classmethod
        def encode(cls, _: np.ndarray) -> bytes:
            """Encode a BGR image to JPEG format.

            Args:
                _: The BGR image to encode (unused - platform
                    not supported).

            Raises:
                RuntimeError: Always raised on unsupported platforms.

            Returns:
                bytes: The encoded JPEG image.

            """
            message = f"Method not implemented for '{sys.platform}'."
            raise RuntimeError(message)

        @classmethod
        def decode(cls, _: bytes) -> np.ndarray:
            """Decode a JPEG image to BGR format.

            Args:
                _: The encoded JPEG image (unused - platform
                    not supported).

            Raises:
                RuntimeError: Always raised on unsupported platforms.

            Returns:
                np.ndarray: The decoded BGR image.

            """
            message = f"Method not implemented for '{sys.platform}'."
            raise RuntimeError(message)
