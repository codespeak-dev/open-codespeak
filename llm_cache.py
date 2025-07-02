from typing import Any, Dict, Iterator, Optional, List
from contextlib import contextmanager
from pathlib import Path
import anthropic
from anthropic.lib.streaming import MessageStream
from anthropic.types import Message

from file_based_cache import FileBasedCache

CACHE_DIR = Path("test_outputs/.llm_cache")
cache = FileBasedCache(CACHE_DIR)


class CachedMessage:
    """A wrapper that mimics Anthropic's Message but from cached data"""
    
    def __init__(self, cached_data: Dict[str, Any]):
        self._data = cached_data
        
    def __getattr__(self, name):
        """Access attributes from the cached data"""
        return self._data.get(name)
    
    @property
    def content(self):
        """Return the content from cached data"""
        return self._data.get('content', [])
    
    @property
    def id(self):
        """Return the id from cached data"""
        return self._data.get('id')
    
    @property
    def model(self):
        """Return the model from cached data"""
        return self._data.get('model')
    
    @property
    def role(self):
        """Return the role from cached data"""
        return self._data.get('role')
    
    @property
    def usage(self):
        """Return the usage from cached data"""
        return self._data.get('usage')
    
    def model_dump(self):
        """Return the cached data as a dict"""
        return self._data
    

class CachedMessageStream:
    """A wrapper that mimics Anthropic's MessageStream but replays cached responses"""
    
    def __init__(self, cached_events: List[Dict[str, Any]], final_message: Message):
        self.cached_events = cached_events
        self.final_message = Message.model_validate(final_message) if final_message is not None else None
        self._text_buffer = []
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        
    @property
    def text_stream(self) -> Iterator[str]:
        """Yield text chunks from cached events"""
        for event in self.cached_events:
            if event['type'] == 'text':
                yield event['text']
                
    def __iter__(self):
        """Iterate over all cached events"""
        for event in self.cached_events:
            yield event

    def get_final_message(self) -> Message:
        """Get the final message from cached events"""
        return self.final_message


class CachedAnthropicClient:
    """A wrapper around Anthropic client that caches messages.stream and messages.create calls"""
    
    def __init__(self, api_key: Optional[str] = None):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.messages = CachedMessagesResource(self._client.messages)
        
    def __getattr__(self, name):
        """Forward all other attributes to the underlying client"""
        return getattr(self._client, name)


class CachedMessagesResource:
    """A wrapper around Anthropic's messages resource that caches stream and create calls"""
    
    def __init__(self, messages_resource):
        self._messages_resource = messages_resource
        
    def __getattr__(self, name):
        """Forward all non-stream attributes to the underlying messages resource"""
        # TODO: remove this
        raise AttributeError(f"Attribute {name} not found")
        # return getattr(self._messages_resource, name)
        
    def create(self, **kwargs) -> Message:
        cache_key = kwargs
        
        cached_response = cache.get(cache_key)
        
        if cached_response is not None:
            # TODO remove
            print(f" !!! Cached response found for {kwargs}")
            try:
                return Message.model_validate(cached_response)
            except (AttributeError, Exception):
                # TODO remove?
                return CachedMessage(cached_response)
        else:
            # TODO remove?
            print(f"No cached response found for {kwargs}")
            response = self._messages_resource.create(**kwargs)
            
            response_dict = response.model_dump() if hasattr(response, 'model_dump') else response.__dict__
            
            cache.set(cache_key, response_dict)
            
            return response
        
    @contextmanager
    def stream(self, **kwargs) -> MessageStream:
        """Cached version of messages.stream"""
        cache_key = kwargs
        cached_response = cache.get(cache_key)
        
        if cached_response is not None:
            # TODO remove
            print(f" !!! Cached response found for {kwargs}")
            try:
                yield CachedMessageStream(cached_response['events_list'], cached_response['final_message'])
            except TypeError:
                print(cached_response)
                raise
        else:
            with self._messages_resource.stream(**kwargs) as stream:
                class CachingStream:
                    def __init__(self, original_stream):
                        self.original_stream = original_stream
                        self.events_list = []
                        self.final_message = None
                        
                    def __getattr__(self, name):
                        return getattr(self.original_stream, name)
                        
                    @property
                    def text_stream(self):
                        for text in self.original_stream.text_stream:
                            self.events_list.append({'type': 'text', 'text': text})
                            yield text
                            
                    def __iter__(self):
                        for event in self.original_stream:
                            self.events_list.append(event)
                            yield event

                    def get_final_message(self) -> Message:
                        self.final_message = self.original_stream.get_final_message()
                        return self.final_message
                
                caching_stream = CachingStream(stream)
                yield caching_stream
                
            cache.set(cache_key, {
                'events_list': caching_stream.events_list,
                'final_message': caching_stream.final_message
            })
    

def create_cached_client(api_key: Optional[str] = None) -> CachedAnthropicClient:
    return CachedAnthropicClient(api_key=api_key)


Anthropic = CachedAnthropicClient
