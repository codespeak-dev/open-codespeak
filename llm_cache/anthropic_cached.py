from contextlib import contextmanager
from copy import deepcopy
from typing import Iterator
from anthropic import Anthropic, AsyncAnthropic
from anthropic.types import Message
from colors import Colors
from file_based_cache import CacheMetadata, FileBasedCache, CacheKey, PersistentCounter, Sanitizer
from pathlib import Path
import logging


DEV_CACHE_DIR = "test_outputs/.llm_cache"
REPORT_CACHE_MISSES = True


class Counter:
    def __init__(self):
        self.counter = 0
    
    def __call__(self):
        self.counter += 1
        return self.counter


class AnthropicSanitizer(Sanitizer):

    def __init__(self, delegate: Sanitizer = None, counter: Counter = None, metadata: CacheMetadata = None):
        self.delegate = delegate or Sanitizer()
        self.sequential_id_counter = counter or Counter()
        self.metadata = metadata
        self.id_map: dict[str, str] = {}

    def sanitize_str(self, text: str) -> str:
        return self.delegate.sanitize_str(text)
    
    def desanitize_str(self, text: str) -> str:
        return self.delegate.desanitize_str(text)

    def sanitize_dict(self, d: dict) -> dict:        
        if "id" in d:
            id_key = "id"
        elif "tool_use_id" in d:
            id_key = "tool_use_id"
        else:
            return d
        
        random_id = d[id_key]
        
        d_copy = deepcopy(d)
        if random_id in self.id_map:
            d_copy[id_key] = self.id_map[random_id]
            return d_copy

        if random_id.startswith("toolu_"):
            prefix = "toolu_"
        elif random_id.startswith("msg_"):
            prefix = "msg_"
        else:
            return d

        sequential_id = f"u_{prefix}{self.sequential_id_counter()}"
        self.id_map[random_id] = sequential_id
        d_copy[id_key] = sequential_id
        return d_copy


class CachedAnthropic:
    client: Anthropic
    async_client: AsyncAnthropic
    base_dir: str

    def __init__(self, base_dir: str, sanitizer: Sanitizer, cache_dir: str = None):
        self.client = Anthropic()
        self.async_client = AsyncAnthropic()
        self.base_dir = base_dir
        
        cache_dir = Path(cache_dir or DEV_CACHE_DIR)
        sanitizer = AnthropicSanitizer(sanitizer, PersistentCounter(cache_dir/".cache_counter"))
        self.cache = FileBasedCache(cache_dir, sanitizer=sanitizer)
        sanitizer.metadata = self.cache.metadata
        
        self.logger = logging.getLogger(CachedAnthropic.__class__.__qualname__)
        
    def report_cache_miss(self, key: CacheKey, info: str):
        if REPORT_CACHE_MISSES:
            info_formatted = info.replace('\n', ' ').strip()
            self.logger.info(f"{Colors.BRIGHT_RED}Cache miss [{key.hash[:8]}]: {info_formatted}{Colors.END}")

    def report_cache_hit(self, key: CacheKey, info: str):
        if REPORT_CACHE_MISSES:
            info_formatted = info.replace('\n', ' ').strip()
            self.logger.info(f"{Colors.BRIGHT_GREEN}Cache hit [{key.hash[:8]}]: {info_formatted}{Colors.END}")

    def create(self, **kwargs) -> Message:
        info = f"create {kwargs.get('system', '<no system prompt>')[:100]}"
        cache_key = self.cache.key_for_callable(self.client.messages.create, **kwargs)
        cached_response = self.cache.get(cache_key)
        if cached_response is not None:
            self.report_cache_hit(cache_key, info)
            return cached_response
        else:
            self.report_cache_miss(cache_key, info)
            result = self.client.messages.create(**kwargs)
            self.cache.set(cache_key, result)
            return result

    async def async_create(self, **kwargs) -> Message:
        info = f"async_create {kwargs.get('system', '<no system prompt>')[:100]}"
        cache_key = self.cache.key_for_callable(self.async_client.messages.create, **kwargs)
        cached_response = self.cache.get(cache_key)
        if cached_response is not None:
            self.report_cache_hit(cache_key, info)
            return cached_response
        else:
            self.report_cache_miss(cache_key, info)
            result = await self.async_client.messages.create(**kwargs)
            self.cache.set(cache_key, result)
            return result
            

    @contextmanager
    def stream(self, **kwargs):
        info = f"stream {kwargs.get('system', '<no system prompt>')[:100]}"
        cache_key = self.cache.key_for_callable(self.client.messages.stream, **kwargs)
        cached_response = self.cache.get(cache_key)
        
        if cached_response is not None:
            self.report_cache_hit(cache_key, info)
            class CachedTextStream:
                @property
                def text_stream(self):
                    for text in cached_response["response_chunks"]:
                        yield text

                def get_final_message(self):
                    return cached_response["final_message"]

            yield CachedTextStream()
        else:        
            self.report_cache_miss(cache_key, info)

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

