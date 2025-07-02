import functools
import time
from contextlib import contextmanager

@contextmanager
def timer_cm(name):
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    print_delta(name, start, end)

def print_delta(name, start, end):
    print(f"\n  * {name}: {(end - start) * 1000:.2f} ms")

def timer_dec(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        print_delta(func.__name__, start, end)
        return result
    return wrapper

def timer(arg):
    if isinstance(arg, str):
        return timer_cm(arg)
    else:
        return timer_dec(arg)