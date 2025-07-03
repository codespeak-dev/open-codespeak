import hashlib
from pathlib import Path
import re
from typing import Any
import json


class CacheKey:
    def __init__(self, key_source: Any):
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
        serializable = make_serializable(raw_source)
        
        if isinstance(serializable, str):
            return serializable
        else:
            return json.dumps(serializable, sort_keys=True, indent=2)


def make_serializable(obj, is_key: bool = False):
    """Convert params to a serializable format, handling Pydantic models"""
    if hasattr(obj, 'model_dump'): 
        return {
            "__pydantic_model_module": obj.__class__.__module__,
            "__pydantic_model_name": obj.__class__.__name__,
            "model_dump": obj.model_dump()
        }
    elif isinstance(obj, dict):
        return {make_serializable(k, is_key=True): make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    elif isinstance(obj, str):
        return obj
    elif isinstance(obj, (int, float, bool)):
        if is_key:
            return str(obj)
        else:
            return obj
    elif obj is None:
        return None
    else:
        raise ValueError(f"Object {obj} is not JSON-compatible")


def get_pydantic_class(dict: dict) -> type:
    import importlib
    module = importlib.import_module(dict["__pydantic_model_module"])
    return getattr(module, dict["__pydantic_model_name"])


def deserialize_with_pydantic(obj: Any) -> Any:
    if isinstance(obj, dict):
        if "__pydantic_model_module" in obj:
            return get_pydantic_class(obj).model_validate(obj["model_dump"])
        else:
            return {
                deserialize_with_pydantic(k): deserialize_with_pydantic(v) 
                for k, v in obj.items()
            }
    elif isinstance(obj, list):
        return [deserialize_with_pydantic(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(deserialize_with_pydantic(item) for item in obj)
    else:
        return obj
    

class FileBasedCache:
    VERSION = (0, 0, 2)
    VERSION_STRING = ".".join(map(str, VERSION))

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
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
            return deserialize_with_pydantic(json.loads(file_name.read_text()))
        
        file_name = self._file_name(key, "txt")
        if file_name.exists():
            return file_name.read_text()
        
        return None
    
    def _set(self, key: CacheKey, value: Any):
        if isinstance(value, str):
            self._file_name(key.hash, "txt").write_text(value)
        else:
            self._file_name(key.hash, "json").write_text(
                json.dumps(make_serializable(value), sort_keys=True, indent=2))

        if isinstance(key._raw_source, str):
            self._file_name(f"{key.hash}.src", "txt").write_text(key.key_source)
        else:
            self._file_name(f"{key.hash}.src", "json").write_text(key.key_source)
    
    def get(self, key: Any) -> Any:
        if isinstance(key, CacheKey):
            return self._get(key)
        else:
            return self._get(CacheKey(key))

    def set(self, key: Any, value: Any):
        if isinstance(key, CacheKey):
            self._set(key, value)
        else:
            self._set(CacheKey(key), value)

    def cache_call(self, callable, **kwargs):
        key = self.key_for_callable(callable, **kwargs)
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value
        else:
            result = callable(**kwargs)
            self.set(key, result)
            return result
        
    def key_for_callable(self, callable, **kwargs) -> CacheKey:
        method_name = f"{callable.__module__}.{callable.__self__.__class__.__name__}.{callable.__name__}"
        return CacheKey({
            "__method_name": method_name,
            "kwargs": kwargs
        })


if __name__ == "__main__":
    cache = FileBasedCache(Path("test_outputs/.test_llm_cache"))
    cache.set(CacheKey("test"), "test")
    cache.set(CacheKey({"a": "b"}), ["test", "test2"])
    cache.set(CacheKey({"a": "b", 2: 1}), "test111")
    cache.set(CacheKey("key"), ["value"])
    print(cache.get(CacheKey("test")))
    print(cache.get(CacheKey({"a": "b"})))
    print(cache.get(CacheKey({"a": "b", 2: 1})))
    print(cache.get(CacheKey("key")))