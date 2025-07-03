from contextlib import contextmanager
from typing import Iterator
from anthropic import Anthropic, AsyncAnthropic
from anthropic.types import Message
from colors import Colors
from file_based_cache import FileBasedCache, CacheKey, Sanitizer
from pathlib import Path
import logging


DEV_CACHE_DIR = "test_outputs/.llm_cache"
REPORT_CACHE_MISSES = True


class CachedAnthropic:
    client: Anthropic
    async_client: AsyncAnthropic
    base_dir: str

    def __init__(self, base_dir: str, sanitizer: Sanitizer, cache_dir: str = None):
        self.client = Anthropic()
        self.async_client = AsyncAnthropic()
        self.base_dir = base_dir
        self.cache = FileBasedCache(Path(cache_dir or DEV_CACHE_DIR), sanitizer=sanitizer)
        self.logger = logging.getLogger(CachedAnthropic.__class__.__qualname__)
        
    def create(self, **kwargs) -> Message:
        cache_key = self.cache.key_for_callable(self.client.messages.create, **kwargs)
        if self.cache.get(cache_key) is not None:
            return self.cache.get(cache_key)
        else:
            self.report_cache_miss(cache_key, f"create {kwargs.get('system', '<no system prompt>')[:100]}")
            result = self.client.messages.create(**kwargs)
            self.cache.set(cache_key, result)
            return result

    def report_cache_miss(self, key: CacheKey, info: str):
        if REPORT_CACHE_MISSES:
            self.logger.info(f"{Colors.BRIGHT_RED}Cache miss [{key.hash[:8]}]: {info}{Colors.END}")

    async def async_create(self, **kwargs) -> Message:
        cache_key = self.cache.key_for_callable(self.async_client.messages.create, **kwargs)
        if self.cache.get(cache_key) is not None:
            return self.cache.get(cache_key)
        else:
            self.report_cache_miss(cache_key, f"async_create {kwargs.get('system', '<no system prompt>')[:100]}")
            result = await self.async_client.messages.create(**kwargs)
            self.cache.set(cache_key, result)
            return result
            
    @contextmanager
    def text_stream(self, **kwargs) -> Iterator[str]:
        cache_key = self.cache.key_for_callable(self.client.messages.stream, **kwargs)
        cached_response = self.cache.get(cache_key)
        
        if cached_response is not None:
            def cached_iterator():
                for text in cached_response:
                    yield text
            yield cached_iterator()
        else:        
            self.report_cache_miss(cache_key, f"stream {kwargs.get('system', '<no system prompt>')[:100]}")
            def stream_iterator():
                with self.client.messages.stream(**kwargs) as stream:
                    response_chunks = []
                    for text in stream.text_stream:
                        response_chunks.append(text)
                        yield text
                    self.cache.set(cache_key, response_chunks)
            yield stream_iterator()

    @contextmanager
    def stream(self, **kwargs):
        cache_key = self.cache.key_for_callable(self.client.messages.stream, **kwargs)
        cached_response = self.cache.get(cache_key)
        
        if cached_response is not None:
            class CachedTextStream:
                @property
                def text_stream(self):
                    for text in cached_response["response_chunks"]:
                        yield text

                def get_final_message(self):
                    return cached_response["final_message"]

            yield CachedTextStream()
        else:        
            self.report_cache_miss(cache_key, f"stream {kwargs.get('system', '<no system prompt>')[:100]}")

            with self.client.messages.stream(**kwargs) as stream:
                response_chunks = []
                final_message = None
                class CachingStream:
                    @property
                    def text_stream(self):
                        for text in stream.text_stream:
                            response_chunks.append(text)
                            yield text

                    def get_final_message(self):
                        nonlocal final_message
                        final_message = stream.get_final_message()
                        return final_message

                yield CachingStream()
                self.cache.set(cache_key, {
                    "response_chunks": response_chunks,
                    "final_message": final_message
                })

