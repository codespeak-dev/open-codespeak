from contextlib import contextmanager
import sys
import threading
import time

from yaspin import yaspin
from yaspin.spinners import Spinners
from colors import Colors



@contextmanager
def with_step(text):
    stop_event = threading.Event()
    elapsed = [0]

    def update_spinner(spinner):
        while not stop_event.is_set():
            spinner.text = f"{text} ({elapsed[0]}s)"
            time.sleep(1)
            elapsed[0] += 1

    with yaspin(Spinners.dots, text=f"{text} (0s)") as spinner:
        t = threading.Thread(target=update_spinner, args=(spinner,))
        t.start()
        try:
            yield
        finally:
            stop_event.set()
            t.join()
            spinner.stop()
            sys.stdout.write("\r" + " " * (len(spinner.text) + 10) + "\r")
            sys.stdout.flush()
            print(f"{text} complete in {elapsed[0]}s.")

@contextmanager
def with_streaming_step(text):
    stop_event = threading.Event()
    elapsed = [0]
    token_count = [0]

    def update_spinner(spinner):
        while not stop_event.is_set():
            if token_count[0] > 0:
                spinner.text = f"{text} {Colors.GREY}{Colors.DIM}({elapsed[0]}s, {token_count[0]} tokens){Colors.END}"
            else:
                spinner.text = f"{text} {Colors.GREY}{Colors.DIM}({elapsed[0]}s){Colors.END}"
            time.sleep(1)
            elapsed[0] += 1

    with yaspin(Spinners.dots, text=f"{text} {Colors.GREY}{Colors.DIM}(0s){Colors.END}") as spinner:
        t = threading.Thread(target=update_spinner, args=(spinner,))
        t.start()
        try:
            yield token_count
        finally:
            stop_event.set()
            t.join()
            spinner.stop()
            sys.stdout.write("\r" + " " * (len(spinner.text) + 10) + "\r")
            sys.stdout.flush()
            if token_count[0] > 0:
                print(f"{text} complete in {Colors.GREY}{Colors.DIM}{elapsed[0]}s ({token_count[0]} tokens){Colors.END}.")
            else:
                print(f"{text} complete in {Colors.GREY}{Colors.DIM}{elapsed[0]}s{Colors.END}.")