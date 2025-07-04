from __future__ import annotations

import os
import time
import threading
import tempfile
import subprocess
import logging
import urllib.request


class Span:
    def __init__(self, name: str, parent: Span | None) -> None:
        self.name = name
        self.children = []
        self.parent = parent
        if parent:
            parent.children.append(self)
        self.start_time = time.time()
        self.end_time = None

    def end(self):
        self.end_time = time.time()


class Flamegraph:
    thread_local_data = threading.local()
    all_root_spans = []
    all_root_spans_lock = threading.Lock()

    @classmethod
    def start_span(cls, name: str):
        if not hasattr(cls.thread_local_data, "current_span"):
            root_span = Span(f"Thread {threading.current_thread().name}", None)
            cls.thread_local_data.root_span = root_span
            cls.thread_local_data.current_span = root_span

            with cls.all_root_spans_lock:
                cls.all_root_spans.append(root_span)

        cls.thread_local_data.current_span = Span(name, cls.thread_local_data.current_span)

    @classmethod
    def end_span(cls):
        if not hasattr(cls.thread_local_data, "current_span"):
            raise ValueError(f"No current span in thread {threading.current_thread().name}")

        current_span = cls.thread_local_data.current_span
        current_span.end()
        if not current_span.parent:
            raise ValueError(f"Cannot end root span {current_span.name}")

        cls.thread_local_data.current_span = current_span.parent

    @classmethod
    def generate_folded_output(cls) -> str:
        result = []

        span_path = []

        def dfs(span, override_span_end_time: float | None) -> float:
            span_path.append(span.name.replace(";", ""))
            span_path_str = ";".join(span_path)

            span_end_time = override_span_end_time if override_span_end_time else span.end_time
            if not span_end_time:
                raise ValueError(f"Span {span_path_str} has not ended")

            self_duration = span_end_time - span.start_time

            total_children_duration = 0
            for child in span.children:
                total_children_duration += dfs(child, override_span_end_time=None)
            span_path.pop()

            if total_children_duration > self_duration:
                raise ValueError(
                    f"Total children duration {total_children_duration} exceeds self duration {self_duration} for span {span_path_str}")

            duration_excluding_children = self_duration - total_children_duration
            result.append(f"{span_path_str}\t{duration_excluding_children}")

            return self_duration

        current_time = time.time()
        with cls.all_root_spans_lock:
            for root_span in cls.all_root_spans:
                dfs(root_span, override_span_end_time=current_time)

        return "\n".join(result)

    @classmethod
    def save_report(cls, project_name, output_path: str):
        logger = logging.getLogger(Flamegraph.__class__.__qualname__)

        flamegraph_url = "https://github.com/brendangregg/FlameGraph/raw/41fee1f99f9276008b7cd112fca19dc3ea84ac32/flamegraph.pl"

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pl', delete=False) as flamegraph_file:
            with urllib.request.urlopen(flamegraph_url) as response:
                flamegraph_file.write(response.read())
            
        flamegraph_pl_path = flamegraph_file.name

        folded_output = cls.generate_folded_output()
        logger.debug(f"Raw report: {folded_output}")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.folded', delete=False) as temp_file:
            temp_file.write(folded_output)

        temp_file_path = temp_file.name

        try:
            result = subprocess.run(
                ["perl", flamegraph_pl_path, temp_file_path, "--countname", "seconds", "--title", f"Run duration: {project_name}"],
                text=True,
                capture_output=True,
                check=False
            )

            if result.returncode == 0:
                with open(output_path, 'w') as output_file:
                    output_file.write(result.stdout)
                    logger.info(f"Report saved to {output_path}")
            else:
                logger.warning(
                    f"Failed to generate report, STDOUT: {result.stdout}, STDERR: {result.stderr}")

        finally:
            os.unlink(temp_file_path)
            os.unlink(flamegraph_pl_path)
