"""
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import Qt

from queue import PriorityQueue
from threading import Thread, Lock

from madqt.core.base import Object, Signal


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
        self.queue.put(((-priority, self.counter), job, callback, args))

    def run(self):
        """Waits for and executes posted jobs in an infinite loop."""
        while True:
            _, job, callback, args = self.queue.get()
            if not job:
                break
            result = job(*args)
            if callback:
                self.dispatch(callback, result)
