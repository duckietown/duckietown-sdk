from typing import Dict

import roslibpy

import cbor2
import json

from roslibpy import Topic, Message
from roslibpy.comm import RosBridgeException
from roslibpy.comm.comm_autobahn import AutobahnRosBridgeProtocol, AutobahnRosBridgeClientFactory


# => This block adds CBOR support to roslibpy ================================================================
#

class RosTopic(Topic):
    SUPPORTED_COMPRESSION_TYPES = ("cbor", "png", "none")


class RosProtocol(AutobahnRosBridgeProtocol):

    def onMessage(self, payload, isBinary):
        if isBinary:
            message = Message(cbor2.loads(payload))
        else:
            message = Message(json.loads(payload.decode("utf8")))

        handler = self._message_handlers.get(message["op"], None)
        if not handler:
            raise RosBridgeException('No handler registered for operation "%s"' % message["op"])

        handler(message)


class RosClientFactory(AutobahnRosBridgeClientFactory):
    protocol = RosProtocol


class Ros(roslibpy.ros.Ros):

    def __init__(self, host, port=None, is_secure=False):
        self._id_counter = 0
        url = RosClientFactory.create_url(host, port, is_secure)
        self.factory = RosClientFactory(url)
        self.is_connecting = False
        self.connect()

#
# <= This block adds CBOR support to roslibpy ================================================================


class ROS:
    _connections: Dict[str, Ros] = {}

    @classmethod
    def get_connection(cls, host: str, port: int = 9001) -> Ros:
        if host in cls._connections:
            return cls._connections[host]
        new: Ros = Ros(host=host, port=port)
        cls._connections[host] = new
        return new
