import hashlib
from pathlib import Path
import re
from typing import Any
import json


class Sanitizer:
    def sanitize(self, text: str) -> str:
        return text

class Serializer:
    def __init__(self, sanitizer: Sanitizer = Sanitizer()):
        self.sanitizer = sanitizer

    def make_serializable(self, obj, is_key: bool = False):
        """Convert params to a serializable format, handling Pydantic models"""
        if hasattr(obj, 'model_dump'): 
            return {
                "__pydantic_model_module": obj.__class__.__module__,
                "__pydantic_model_name": obj.__class__.__name__,
                "model_dump": self.make_serializable(obj.model_dump(), is_key=is_key)
            }
        elif isinstance(obj, dict):
            return {self.make_serializable(k, is_key=True): self.make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self.make_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return self.make_serializable(obj.__dict__, is_key=is_key)
        elif isinstance(obj, str):
            return self.sanitizer.sanitize(obj)
        elif isinstance(obj, (int, float, bool)):
            if is_key:
                return str(obj)
            else:
                return obj
        elif obj is None:
            return None
        else:
            raise ValueError(f"Object {obj} is not JSON-compatible")

    def get_pydantic_class(self, dict: dict) -> type:
        import importlib
        module = importlib.import_module(dict["__pydantic_model_module"])
        return getattr(module, dict["__pydantic_model_name"])

    def deserialize_with_pydantic(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            if "__pydantic_model_module" in obj:
                return self.get_pydantic_class(obj).model_validate(obj["model_dump"])
            else:
                return {
                    self.deserialize_with_pydantic(k): self.deserialize_with_pydantic(v) 
                    for k, v in obj.items()
                }
        elif isinstance(obj, list):
            return [self.deserialize_with_pydantic(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self.deserialize_with_pydantic(item) for item in obj)
        else:
            return obj
    

class CacheKey:
    def __init__(self, key_source: Any, serializer: Serializer):
        self.serializer = serializer
        self._raw_source = key_source
        self._prepared_source = self._make_hashable(key_source)
        self._hash = hashlib.sha256(self._prepared_source.encode()).hexdigest()
        
    def __hash__(self):
        return hash(self.hash)
    
    def __eq__(self, other):
        return self.hash == other.hash

    def __str__(self):
        return self.hash
    
    @property
    def hash(self) -> str:
        return self._hash
    
    @property
    def key_source(self) -> str:
        return self._prepared_source

    def _make_hashable(self, raw_source: Any) -> str:        
        serializable = self.serializer.make_serializable(raw_source)
        
        if isinstance(serializable, str):
            return serializable
        else:
            return json.dumps(serializable, sort_keys=True, indent=2)


class FileBasedCache:
    VERSION = (0, 0, 2)
    VERSION_STRING = ".".join(map(str, VERSION))

    def __init__(self, cache_dir: Path, key_sanitizer: Sanitizer = Sanitizer()):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.key_serializer = Serializer(key_sanitizer)
        self.value_serializer = Serializer()

        version_file = self.cache_dir.joinpath(".version")
        if not version_file.exists():
            version_file.write_text(self.VERSION_STRING)
        else:
            version = version_file.read_text().strip()
            # don't accept higher versions
            # parse version from file
            match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
            if not match:
                raise ValueError(f"Wrong version format in {version_file}: {version}. Consider clearing the cache")
            if int(match.group(1)) > self.VERSION[0] or int(match.group(2)) > self.VERSION[1] or int(match.group(3)) > self.VERSION[2]:
                raise ValueError(f"Cache version mismatch: {version} > {self.VERSION_STRING}. Consider clearing the cache")

    def _file_name(self, key: str, file_type: str) -> Path:
        return self.cache_dir.joinpath(f"{key}.{file_type}")

    def _get(self, key: CacheKey) -> Any:
        file_name = self._file_name(key, "json")
        if file_name.exists():
            return self.value_serializer.deserialize_with_pydantic(json.loads(file_name.read_text()))
        
        file_name = self._file_name(key, "txt")
        if file_name.exists():
            return file_name.read_text()
        
        return None
    
    def _set(self, key: CacheKey, value: Any):
        if isinstance(value, str):
            self._file_name(key.hash, "txt").write_text(value)
        else:
            self._file_name(key.hash, "json").write_text(
                json.dumps(self.value_serializer.make_serializable(value), sort_keys=True, indent=2))

        if isinstance(key._raw_source, str):
            self._file_name(f"{key.hash}.src", "txt").write_text(key.key_source)
        else:
            self._file_name(f"{key.hash}.src", "json").write_text(key.key_source)
    
    def get(self, key: Any) -> Any:
        if isinstance(key, CacheKey):
            return self._get(key)
        else:
            return self._get(self.key(key))

    def set(self, key: Any, value: Any):
        if isinstance(key, CacheKey):
            self._set(key, value)
        else:
            self._set(self.key(key), value)

    def cache_call(self, callable, **kwargs):
        key = self.key_for_callable(callable, **kwargs)
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value
        else:
            result = callable(**kwargs)
            self.set(key, result)
            return result

    def key(self, key_source: Any) -> CacheKey:
        return CacheKey(key_source, self.key_serializer)
    
    def key_for_callable(self, callable, **kwargs) -> CacheKey:
        method_name = f"{callable.__module__}.{callable.__self__.__class__.__name__}.{callable.__name__}"
        return self.key({
            "__method_name": method_name,
            "kwargs": kwargs
        })


if __name__ == "__main__":
    from llm_cache.cache_utils import SubstringBasedSanitizer
    from anthropic.types.tool_use_block import ToolUseBlock
    tub = ToolUseBlock(
        **{
              "id": "toolu_01XaSTkQbsBABbD4qtnRDs5J",
              "input": {
                "file_path": "31_helloworld/urls.py"
              },
              "name": "read_file",
              "type": "tool_use"
            }
    )

    print(type(tub))
    print(tub.model_dump())
    print(type(tub.input))
    dict0 = Serializer(SubstringBasedSanitizer([("31_hello", "!!!!fuck")])).make_serializable([tub], is_key=True)
    print(dict0)
    xxx = Serializer().deserialize_with_pydantic(dict0)
    print(xxx)
    print(type(xxx))
    # print(xxx.model_dump())
    import sys
    sys.exit()

    cache = FileBasedCache(Path("test_outputs/.test_llm_cache"))
    cache.set(cache.key("test"), "test")
    cache.set(cache.key({"a": "b"}), ["test", "test2"])
    cache.set(cache.key({"a": "b", 2: 1}), "test111")
    cache.set(cache.key("key"), ["value"])
    logger.info(cache.get(cache.key("test")))
    logger.info(cache.get(cache.key({"a": "b"})))
    logger.info(cache.get(cache.key({"a": "b", 2: 1})))
    logger.info(cache.get(cache.key("key")))