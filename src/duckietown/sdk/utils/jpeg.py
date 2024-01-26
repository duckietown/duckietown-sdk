# use turbojpeg on linux, pillow on macos
import io
import sys
from abc import ABC, abstractmethod

import numpy as np

from duckietown.sdk.types import BGRImage


class JPEGAbs(ABC):

    @classmethod
    @abstractmethod
    def encode(cls, image: BGRImage) -> bytes:
        pass

    @classmethod
    @abstractmethod
    def decode(cls, data: bytes) -> BGRImage:
        pass


if sys.platform == "linux":
    import turbojpeg
    jpeg: turbojpeg.TurboJPEG = turbojpeg.TurboJPEG()

    class JPEG(JPEGAbs):

        @classmethod
        def encode(cls, image: BGRImage) -> bytes:
            return jpeg.encode(image)


        @classmethod
        def decode(cls, data: bytes) -> BGRImage:
            return jpeg.decode(data)

elif sys.platform == "darwin":
    from PIL import Image

    class JPEG(JPEGAbs):

        @classmethod
        def encode(cls, image: BGRImage) -> bytes:
            buf: io.BytesIO = io.BytesIO()
            Image.fromarray(image).save(buf, format="JPEG")
            return buf.getvalue()

        @classmethod
        def decode(cls, data: bytes) -> BGRImage:
            return np.array(Image.open(io.BytesIO(data)))
else:

    class JPEG(JPEGAbs):

        @classmethod
        def encode(cls, image: BGRImage) -> bytes:
            raise RuntimeError(f"Method JPEG.encode() not implemented for system '{sys.platform}'")

        @classmethod
        def decode(cls, data: bytes) -> BGRImage:
            raise RuntimeError(f"Method JPEG.decode() not implemented for system '{sys.platform}'")
