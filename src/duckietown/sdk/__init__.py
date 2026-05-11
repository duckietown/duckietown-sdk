"""Duckietown SDK."""

__version__ = "0.2.0"

import logging
import sys

from duckietown.sdk.compat import enable_python38_compat

if sys.version_info < (3, 9):
	enable_python38_compat()

logging.basicConfig()
logger = logging.getLogger("duckietown-sdk")
logger.setLevel(logging.INFO)
