#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

# A simple broker for simulating broker clients. Shamelessly stolen from the
# proton python examples.  Accepts incoming links and forwards messages based
# on target address.

from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function

import collections
from threading import Thread
import uuid

from proton import Message
from proton import Endpoint
from proton.handlers import MessagingHandler
from proton.reactor import Container
from proton.reactor import AtMostOnce

from system_test import TIMEOUT


class FakeBroker(MessagingHandler):
    """
    A fake broker-like service that listens for client connections
    """
    class _Queue(object):
        def __init__(self, dynamic=False):
            self.dynamic = dynamic
            self.queue = collections.deque()
            self.consumers = []

        def subscribe(self, consumer):
            self.consumers.append(consumer)

        def unsubscribe(self, consumer):
            if consumer in self.consumers:
                self.consumers.remove(consumer)
            return len(self.consumers) == 0 and (self.dynamic or len(self.queue) == 0)

        def publish(self, message):
            self.queue.append(message)
            return self.dispatch()

        def dispatch(self, consumer=None):
            if consumer:
                c = [consumer]
            else:
                c = self.consumers
            count = 0
            while True:
                rc = self._deliver_to(c)
                count += rc
                if rc == 0:
                    break;
            return count

        def _deliver_to(self, consumers):
            try:
                result = 0
                for c in consumers:
                    if c.credit:
                        c.send(self.queue.popleft())
                        result += 1
                return result
            except IndexError: # no more messages
                return 0

    def __init__(self, url, container_id=None, **handler_kwargs):
        super(FakeBroker, self).__init__(**handler_kwargs)
        self.url = url
        self.queues = {}
        self.acceptor = None
        self.in_count = 0
        self.out_count = 0
        self._connections = []
        self._error = None
        self._container = Container(self)
        self._container.container_id = container_id or 'FakeBroker'
        self._thread = Thread(target=self._main)
        self._thread.daemon = True
        self._stop_thread = False
        self._thread.start()

    def _main(self):
        self._container.timeout = 1.0
        self._container.start()

        while self._container.process():
            if self._stop_thread:
                if self.acceptor:
                    self.acceptor.close()
                    self.acceptor = None
                for c in self._connections:
                    c.close()
                self._connections = []

    def join(self):
        self._stop_thread = True
        self._container.wakeup()
        self._thread.join(timeout=TIMEOUT)
        if self._thread.is_alive():
            raise Exception("FakeBroker did not exit")
        if self._error:
            raise Exception(self._error)

    def on_start(self, event):
        self.acceptor = event.container.listen(self.url)

    def _queue(self, address):
        if address not in self.queues:
            self.queues[address] = self._Queue()
        return self.queues[address]

    def on_link_opening(self, event):
        if event.link.is_sender:
            if event.link.remote_source.dynamic:
                address = str(uuid.uuid4())
                event.link.source.address = address
                q = self._Queue(True)
                self.queues[address] = q
                q.subscribe(event.link)
            elif event.link.remote_source.address:
                event.link.source.address = event.link.remote_source.address
                self._queue(event.link.source.address).subscribe(event.link)
        elif event.link.remote_target.address:
            event.link.target.address = event.link.remote_target.address

    def _unsubscribe(self, link):
        if link.source.address in self.queues and self.queues[link.source.address].unsubscribe(link):
            del self.queues[link.source.address]

    def on_link_closing(self, event):
        if event.link.is_sender:
            self._unsubscribe(event.link)

    def on_connection_opening(self, event):
        pn_conn = event.connection
        pn_conn.container = self._container.container_id

    def on_connection_opened(self, event):
        self._connections.append(event.connection)

    def on_connection_closing(self, event):
        self.remove_stale_consumers(event.connection)

    def on_connection_closed(self, event):
        try:
            self._connections.remove(event.connection)
        except ValueError:
            pass

    def on_disconnected(self, event):
        self.remove_stale_consumers(event.connection)

    def remove_stale_consumers(self, connection):
        link = connection.link_head(Endpoint.REMOTE_ACTIVE)
        while link:
            if link.is_sender:
                self._unsubscribe(link)
            link = link.next(Endpoint.REMOTE_ACTIVE)

    def on_sendable(self, event):
        self.out_count += self._queue(event.link.source.address).dispatch(event.link)

    def on_message(self, event):
        self.in_count += 1
        self.out_count += self._queue(event.link.target.address).publish(event.message)


class FakeService(FakeBroker):
    """
    Like a broker, but proactively connects to the message bus
    Useful for testing link routes
    """
    def __init__(self, url, container_id=None):
        super(FakeService, self).__init__(url, container_id)

    def on_start(self, event):
        event.container.connect(url=self.url)
