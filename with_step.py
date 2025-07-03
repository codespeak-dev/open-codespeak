from contextlib import contextmanager
import sys
import threading
import time
import logging

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
            logger = logging.getLogger("with_step")
            logger.info(f"{text} complete in {elapsed[0]}s.")

@contextmanager
def with_streaming_step(text):
    stop_event = threading.Event()
    elapsed = [0]
    input_tokens = [0]
    output_tokens = [0]

    def update_spinner(spinner):
        while not stop_event.is_set():
            if output_tokens[0] > 0:
                spinner.text = f"{text} {Colors.GREY}{Colors.DIM}({elapsed[0]}s, ↑ {input_tokens[0]} + ↓ {output_tokens[0]} tokens){Colors.END}"
            else:
                spinner.text = f"{text} {Colors.GREY}{Colors.DIM}({elapsed[0]}s){Colors.END}"
            time.sleep(1)
            elapsed[0] += 1

    with yaspin(Spinners.dots, text=f"{text} {Colors.GREY}{Colors.DIM}(0s){Colors.END}") as spinner:
        t = threading.Thread(target=update_spinner, args=(spinner,))
        t.start()
        try:
            yield (input_tokens, output_tokens)
        finally:
            stop_event.set()
            t.join()
            spinner.stop()
            sys.stdout.write("\r" + " " * (len(spinner.text) + 10) + "\r")
            sys.stdout.flush()
            logger = logging.getLogger("with_streaming_step")
            if output_tokens[0] > 0:
                logger.info(f"{text} complete in {Colors.GREY}{Colors.DIM}{elapsed[0]}s (↑ {input_tokens[0]} + ↓ {output_tokens[0]} tokens){Colors.END}.")
            else:
                logger.info(f"{text} complete in {Colors.GREY}{Colors.DIM}{elapsed[0]}s{Colors.END}.")