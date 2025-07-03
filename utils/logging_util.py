import functools
import logging
import typing
from datetime import datetime, timezone
from os import linesep

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

ENABLE_OPEN_TRACE = False

class IndentingFormatter(logging.Formatter):
    def __init__(self, fmt=None):
        super().__init__(fmt)
        self.indent_level = 0
        self.indent_str = '\t'

    def indent_increase(self) -> int:
        self.indent_level += 1
        return self.indent_level

    def indent_decrease(self) -> int:
        if self.indent_level > 0:
            self.indent_level -= 1
        else:
            raise ValueError("Cannot decrease indent")
        return self.indent_level

    def format(self, record):
        original_msg = super().format(record)
        indent = self.indent_str * self.indent_level
        result_msg = indent + original_msg.replace('\n', '\\n')
        return result_msg

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.isoformat()


class LoggerSpanExporter(SpanExporter):

    def __init__(self):
        self.formatter = lambda span: span.to_json() + linesep
        self.logger = logging.getLogger("SpanLogger")

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            self.logger.info(self.formatter(span))
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class LoggingUtil:
    initialized = False
    tracer = None

    @classmethod
    def initialize_logger(cls, log_file_path: str):
        logger = logging.getLogger()  # root logger
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        file_handler = logging.FileHandler(log_file_path)
        formatter = IndentingFormatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.addHandler(logging.StreamHandler())  # no indent

        if ENABLE_OPEN_TRACE:
            trace_provider = TracerProvider()
            trace_provider.add_span_processor(SimpleSpanProcessor(LoggerSpanExporter()))
            trace.set_tracer_provider(trace_provider)

        cls.tracer = trace.get_tracer("CodeSpeak")
        cls.initialized = True

    @classmethod
    def ensure_initialized(cls):
        if not cls.initialized:
            raise ValueError("Please call LoggingUtil.initialize()")

    @staticmethod
    def span(name: str):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                def delegate():
                    return func(*args, **kwargs)

                LoggingUtil.run_in_span(delegate, name, func)

            return wrapper

        return decorator

    @classmethod
    def enter_span(cls, name: str, annotated_function=None):
        cls.ensure_initialized()
        cause = f"annotated function: {annotated_function.__qualname__}" if annotated_function else "explicitly"

        # for unnamed spans, just increase indent
        if name:
            logging.getLogger(LoggingUtil.__class__.__qualname__).info(f"Starting span: {name}")
        new_depth = LoggingUtil._find_indenter().indent_increase()

        logging.getLogger(LoggingUtil.__class__.__qualname__).debug(
            f"Started span: {name if name else 'empty'}, {cause}, new depth: {new_depth}")

        span = cls.tracer.start_as_current_span(name if name else "(unnamed)")
        span.__enter__()

    @classmethod
    def exit_span(cls, name: str, annotated_function=None):
        LoggingUtil.ensure_initialized()
        new_depth = LoggingUtil._find_indenter().indent_decrease()
        cause = f"annotated function: {annotated_function.__qualname__}" if annotated_function else "explicitly"
        logging.getLogger(LoggingUtil.__class__.__qualname__).debug(f"Exited span: {name}, {cause}, new depth: {new_depth}")

        trace.get_current_span().__exit__(None, None, None)

    @classmethod
    def _find_indenter(cls) -> IndentingFormatter:
        file_handler = next((handler for handler in logging.getLogger().handlers if isinstance(handler, logging.FileHandler)), None)
        return file_handler.formatter

    @staticmethod
    def run_in_span(func, span_name: str, annotated_function=None):
        LoggingUtil.enter_span(span_name, annotated_function)
        try:
            return func()
        finally:
            LoggingUtil.exit_span(span_name, annotated_function)

    class Span:
        def __init__(self, name: str) -> None:
            self.name = name

        def __enter__(self):
            LoggingUtil.enter_span(self.name)

        def __exit__(self, exc_type, exc_val, exc_tb):
            LoggingUtil.exit_span(self.name)
            return False