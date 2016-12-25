try:
    import utime as time
except ImportError:
    import time
try:
    from utimeq import utimeq
except ImportError:
    class utimeq(object):
        # Simple utimeq drop-in
        _q = list()
        def __new__(cls, len=128):
            self = super(utimeq, cls).__new__(cls)
            self.__dict__ = None  # Garbage collect unneeded instance dict
            return self
        def push(self, *args):
            self._q.append(args)
        def pop(self, l):
            l[:] = list(self._q.pop(0))
        def __len__(self):
            return len(self._q)
import logging


DEBUG = 0

log = logging.getLogger("asyncio")

type_gen = type((lambda: (yield))())


class EventLoop:
    def __init__(self, len=128):
        self.q = utimeq(len)

    def time(self):
        return time.ticks_ms()

    def create_task(self, coro):
        # CPython 3.4.2
        self.call_later_ms_(0, coro)
        # CPython asyncio incompatibility: we don't return Task object

    def call_soon(self, callback, *args):
        self.call_at(self.time(), callback, *args)

    def call_later(self, delay, callback, *args):
        self.call_at(time.ticks_add(self.time(), int(delay * 1000)), callback, *args)

    def call_later_ms_(self, delay, callback, args=()):
        self.call_at_(time.ticks_add(self.time(), delay), callback, args)

    def call_at(self, time, callback, *args):
        if __debug__ and DEBUG:
            log.debug("Scheduling %s", (time, callback, args))
        self.q.push(time, callback, args)

    def call_at_(self, time, callback, args=()):
        if __debug__ and DEBUG:
            log.debug("Scheduling %s", (time, callback, args))
        self.q.push(time, callback, args)

    def wait(self, delay):
        # Default wait implementation, to be overriden in subclasses
        # with IO scheduling
        if __debug__ and DEBUG:
            log.debug("Sleeping for: %s", delay)
        time.sleep_ms(delay)

    def run_forever(self):
        cur_task = [0, 0, 0]
        while True:
            if self.q:
                self.q.pop(cur_task)
                t = cur_task[0]
                cb = cur_task[1]
                args = cur_task[2]
                if __debug__ and DEBUG:
                    log.debug("Next coroutine to run: %s", (t, cb, args))
#                __main__.mem_info()
                tnow = self.time()
                delay = time.ticks_diff(t, tnow)
                if delay > 0:
                    self.wait(delay)
            else:
                self.wait(-1)
                # Assuming IO completion scheduled some tasks
                continue
            if callable(cb):
                cb(*args)
            else:
                delay = 0
                try:
                    if __debug__ and DEBUG:
                        log.debug("Coroutine %s send args: %s", cb, args)
                    if args == ():
                        ret = next(cb)
                    else:
                        ret = cb.send(*args)
                    if __debug__ and DEBUG:
                        log.debug("Coroutine %s yield result: %s", cb, ret)
                    if isinstance(ret, SysCall1):
                        sock = ret.arg
                        if isinstance(ret, Sleep):
                            delay = int(arg * 1000)
                        elif isinstance(ret, IORead):
#                            self.add_reader(ret.obj.fileno(), lambda self, c, f: self.call_soon(c, f), self, cb, ret.obj)
#                            self.add_reader(ret.obj.fileno(), lambda c, f: self.call_soon(c, f), cb, ret.obj)
#                            self.add_reader(arg.fileno(), lambda cb: self.call_soon(cb), cb)
                            self.add_reader(sock, cb)
                            continue
                        elif isinstance(ret, IOWrite):
#                            self.add_writer(arg.fileno(), lambda cb: self.call_soon(cb), cb)
                            self.add_writer(sock, cb)
                            continue
                        elif isinstance(ret, IOReadDone):
                            self.remove_reader(sock)
                        elif isinstance(ret, IOWriteDone):
                            self.remove_writer(sock)
                        elif isinstance(ret, StopLoop):
                            return arg
                    elif isinstance(ret, type_gen):
                        self.call_soon(ret)
                    elif isinstance(ret, int):
                        # Delay
                        delay = ret
                    elif ret is None:
                        # Just reschedule
                        pass
                    else:
                        assert False, "Unsupported coroutine yield value: %r (of type %r)" % (ret, type(ret))
                except StopIteration as e:
                    if __debug__ and DEBUG:
                        log.debug("Coroutine finished: %s", cb)
                    continue
                self.call_later_ms_(delay, cb, args)

    def run_until_complete(self, coro):
        def _run_and_stop():
            yield from coro
            yield StopLoop(0)
        self.call_soon(_run_and_stop())
        self.run_forever()

    def close(self):
        pass


class SysCall:

    def __init__(self, *args):
        self.args = args

    def handle(self):
        raise NotImplementedError

# Optimized syscall with 1 arg
class SysCall1(SysCall):

    def __init__(self, arg):
        self.arg = arg

class Sleep(SysCall1):
    pass

class StopLoop(SysCall1):
    pass

class IORead(SysCall1):
    pass

class IOWrite(SysCall1):
    pass

class IOReadDone(SysCall1):
    pass

class IOWriteDone(SysCall1):
    pass


_event_loop = None
_event_loop_class = EventLoop
def get_event_loop():
    global _event_loop
    if _event_loop is None:
        _event_loop = _event_loop_class()
    return _event_loop

def sleep(secs):
    yield int(secs * 1000)

def sleep_ms(ms):
    yield ms

def coroutine(f):
    return f

#
# The functions below are deprecated in uasyncio, and provided only
# for compatibility with CPython asyncio
#

def ensure_future(coro, loop=_event_loop):
    _event_loop.call_soon(coro)
    # CPython asyncio incompatibility: we don't return Task object
    return coro


# CPython asyncio incompatibility: Task is a function, not a class (for efficiency)
def Task(coro, loop=_event_loop):
    # Same as async()
    _event_loop.call_soon(coro)
