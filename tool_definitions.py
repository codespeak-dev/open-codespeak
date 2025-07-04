"""
Typed tool definitions with provider-agnostic converters
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
import json


@dataclass
class ToolParameter:
    """Represents a tool parameter with full typing support"""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None
    items: Optional['ToolParameter'] = None  # For array types
    properties: Optional[Dict[str, 'ToolParameter']] = None  # For object types


@dataclass
class Tool:
    """Provider-agnostic tool definition with full typing"""
    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to standard JSON Schema format"""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = self._parameter_to_schema(param)
            if param.required:
                required.append(param.name)

        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False
        }

        if required:
            schema["required"] = required

        return schema

    def _parameter_to_schema(self, param: ToolParameter) -> Dict[str, Any]:
        """Convert a ToolParameter to JSON Schema"""
        schema = {
            "type": param.type,
            "description": param.description
        }

        if param.default is not None:
            schema["default"] = param.default

        if param.enum:
            schema["enum"] = param.enum

        if param.type == "array" and param.items:
            schema["items"] = self._parameter_to_schema(param.items)

        if param.type == "object" and param.properties:
            schema["properties"] = {}
            required = []
            for prop_name, prop_param in param.properties.items():
                schema["properties"][prop_name] = self._parameter_to_schema(prop_param)
                if prop_param.required:
                    required.append(prop_name)
            if required:
                schema["required"] = required
        
        return schema


# Provider conversion functions

def to_anthropic(tool: Tool):
    """Convert Tool to Anthropic ToolParam format"""
    try:
        from anthropic.types import ToolParam
        return ToolParam(
            name=tool.name,
            description=tool.description,
            input_schema=tool.to_json_schema()
        )
    except ImportError:
        raise ImportError("anthropic package not available")


def to_openai(tool: Tool) -> Dict[str, Any]:
    """Convert Tool to OpenAI function format"""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.to_json_schema()
        }
    }


def to_gemini(tool: Tool):
    """Convert Tool to Gemini FunctionDeclaration format"""
    try:
        from google.genai import types as gemini_types
        
        # Convert parameters to Gemini Schema format
        properties = {}
        required = []
        
        for param in tool.parameters:
            properties[param.name] = _parameter_to_gemini_schema(param)
            if param.required:
                required.append(param.name)
        
        function_decl = gemini_types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=gemini_types.Schema(
                type=gemini_types.Type.OBJECT,
                properties=properties,
                required=required
            )
        )
        
        return gemini_types.Tool(function_declarations=[function_decl])
        
    except ImportError:
        raise ImportError("google.genai package not available")


def _parameter_to_gemini_schema(param: ToolParameter):
    """Convert ToolParameter to Gemini Schema"""
    from google.genai import types as gemini_types

    # Map types to Gemini types
    type_mapping = {
        "string": gemini_types.Type.STRING,
        "integer": gemini_types.Type.INTEGER,
        "boolean": gemini_types.Type.BOOLEAN,
        "array": gemini_types.Type.ARRAY,
        "object": gemini_types.Type.OBJECT
    }

    gemini_type = type_mapping.get(param.type, gemini_types.Type.STRING)
    
    schema = gemini_types.Schema(
        type=gemini_type,
        description=param.description
    )

    # Handle nested structures
    if param.type == "array" and param.items:
        schema.items = _parameter_to_gemini_schema(param.items)

    if param.type == "object" and param.properties:
        properties = {}
        required = []
        for prop_name, prop_param in param.properties.items():
            properties[prop_name] = _parameter_to_gemini_schema(prop_param)
            if prop_param.required:
                required.append(prop_name)
        schema.properties = properties
        if required:
            schema.required = required
    
    return schema


# Convenience functions for multiple tools

def to_anthropic_list(tools: List[Tool]) -> List:
    """Convert list of Tools to Anthropic format"""
    return [to_anthropic(tool) for tool in tools]


def to_openai_list(tools: List[Tool]) -> List[Dict[str, Any]]:
    """Convert list of Tools to OpenAI format"""
    return [to_openai(tool) for tool in tools]


def to_gemini_list(tools: List[Tool]) -> List:
    """Convert list of Tools to Gemini format"""
    try:
        from google.genai import types as gemini_types
        
        function_declarations = []
        for tool in tools:
            gemini_tool = to_gemini(tool)
            function_declarations.extend(gemini_tool.function_declarations)
        
        return [gemini_types.Tool(function_declarations=function_declarations)]
        
    except ImportError:
        raise ImportError("google.genai package not available")


# Helper functions for creating common parameter types

def string_param(name: str, description: str, required: bool = False, 
                enum: Optional[List[str]] = None, default: Any = None) -> ToolParameter:
    """Create a string parameter"""
    return ToolParameter(
        name=name, 
        type="string", 
        description=description, 
        required=required,
        enum=enum,
        default=default
    )


def integer_param(name: str, description: str, required: bool = False, 
                 default: Any = None) -> ToolParameter:
    """Create an integer parameter"""
    return ToolParameter(
        name=name, 
        type="integer", 
        description=description, 
        required=required,
        default=default
    )


def boolean_param(name: str, description: str, required: bool = False, 
                 default: Any = None) -> ToolParameter:
    """Create a boolean parameter"""
    return ToolParameter(
        name=name, 
        type="boolean", 
        description=description, 
        required=required,
        default=default
    )


def array_param(name: str, description: str, items: ToolParameter, 
               required: bool = False) -> ToolParameter:
    """Create an array parameter"""
    return ToolParameter(
        name=name, 
        type="array", 
        description=description, 
        required=required,
        items=items
    )


def object_param(name: str, description: str, properties: Dict[str, ToolParameter], 
                required: bool = False) -> ToolParameter:
    """Create an object parameter"""
    return ToolParameter(
        name=name, 
        type="object", 
        description=description, 
        required=required,
        properties=properties
    )
