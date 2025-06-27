from copy import deepcopy
import json
import os
from typing import Any


class SchemaError(Exception):
    pass

def validate_schema_entry(schema_entry: dict) -> bool:
    if schema_entry.get("type") == "file":
        if not schema_entry.get("relative_path"):
            raise SchemaError(f"Relative path is required for file type")
        if not schema_entry.get("format"):
            raise SchemaError(f"Format is required for file type")
        if not schema_entry.get("format") in ["json", "text"]:
            raise SchemaError(f"Invalid format for file type: {schema_entry.get('format')}")
    else:
        raise SchemaError(f"Unknown schema type: {schema_entry.get('type')}")
    
def json_file(relative_path: str) -> Any:
    return {
        "type": "file",
        "relative_path": relative_path,
        "format": "json"
    }

def text_file(relative_path: str) -> Any:
    return {
        "type": "file",
        "relative_path": relative_path,
        "format": "text"
    }

def encode_data(data: Any, schema: dict, base_path: str) -> Any:
    if isinstance(data, dict):
        result = deepcopy(data)
        for key, value in data.items():
            schema_entry = schema.get(key)
            if schema_entry:
                if schema_entry.get("type") == "file":
                    relative_path = schema_entry["relative_path"]
                    with open(os.path.join(base_path, relative_path), "w") as f:
                        if schema_entry.get("format") == "json":
                            json.dump(value, f, indent=4, ensure_ascii=False)
                        elif schema_entry.get("format") == "text":
                            f.write(value)
                        else:
                            raise SchemaError(f"Invalid format for file type: {schema_entry.get('format')}")
                    result[key] = relative_path
        return result
    
    if isinstance(data, list):
        return [encode_data(item, schema, base_path) for item in data]
    
    return data

def decode_data(data: Any, schema: dict, base_path: str) -> Any:
    if isinstance(data, dict):
        result = deepcopy(data)
        for key, value in data.items():
            schema_entry = schema.get(key)
            if schema_entry:
                if schema_entry.get("type") == "file":
                    relative_path = schema_entry["relative_path"]

                    with open(os.path.join(base_path, relative_path), "r") as f:
                        if schema_entry.get("format") == "json":
                            result[key] = json.load(f)
                        elif schema_entry.get("format") == "text":
                            result[key] = f.read()
        return result
    
    if isinstance(data, list):
        return [decode_data(item, schema, base_path) for item in data]
    
    return data
