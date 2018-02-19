"""
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madgui.qt import Qt, QtGui

import time
from queue import PriorityQueue
from threading import Thread, Lock

from madgui.core.base import Object, Signal


def call(func, args, kwargs):
    func(*args, **kwargs)


class QueuedDispatcher(Object):

    """
    Executes callbacks in the thread determined by the thread affinity of the
    object.
    """

    notify = Signal([object, object, object])

    def __init__(self):
        super().__init__()
        self.notify.connect(call, Qt.QueuedConnection)

    def __call__(*args, **kwargs):
        """Schedule the callback for execution in the main thread."""
        self, func, *args = args
        # Note: Qt signal emission is thread safe!
        self.notify.emit(func, args, kwargs)


class WorkerThread(Thread):

    def __init__(self, dispatcher=None):
        self.queue = PriorityQueue()
        self.dispatch = dispatcher or QueuedDispatcher()
        self.counter = 0
        self.lock = Lock()
        QtGui.QApplication.instance().aboutToQuit.connect(self.quit)
        super().__init__()

    def quit(self):
        self.post(None)

    def post(self, job, callback=None, priority=0, args=()):
        """Higher priority jobs will be scheduled earlier."""
        with self.lock:
            count = self.counter
            self.counter += 1
        self.queue.put(((-priority, count), job, callback, args))

    def run(self):
        """Waits for and executes posted jobs in an infinite loop."""
        while True:
            _, job, callback, args = self.queue.get()
            if not job:
                break
            result = job(*args)
            if callback:
                self.dispatch(callback, result)


def spawn(*args, **kwargs):
    func, *args = args
    thread = Thread(target=func, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()
    return thread


class fetch_all:

    def __init__(self, iterable, callback, block=False, dispatcher=None):
        iterable = iter(iterable)
        download, self._more = self._fetch_blocking(iterable, block)
        if self._more:
            self._dispatch = dispatcher or QueuedDispatcher()
            self._thread = spawn(
                self._thread_main, iterable, download, callback)
        else:
            callback(download)

    def stop(self):
        if self._more:
            self._more = False
            self._thread.join()
            self._thread = None

    def _fetch_blocking(self, iterable, timeout):
        if timeout in (0, False):
            return [], True
        if timeout in (-1, None) or timeout is True:
            return list(iterable), False
        timeout = time.time() + timeout
        download = []
        for item in iterable:
            download.append(item)
            if time.time() > timeout:
                return download, True
        return download, False

    def _thread_main(self, iterable, download, callback):
        for item in iterable:
            download.append(item)
            if not self._more:
                return
        self._dispatch(callback, download)
