"""
Unified LLM Interface for Claude, Gemini, and OpenAI
Provides a consistent API for tool/function calling across all providers
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import json
import os


class LLMProvider(Enum):
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI = "openai"


@dataclass
class ToolParameter:
    """Represents a single tool parameter"""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None
    properties: Optional[Dict[str, 'ToolParameter']] = None  # For object types


@dataclass
class UnifiedTool:
    """Unified tool definition that works across all providers"""
    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    
    def get_required_parameters(self) -> List[str]:
        """Get list of required parameter names"""
        return [p.name for p in self.parameters if p.required]
    
    def get_parameter_by_name(self, name: str) -> Optional[ToolParameter]:
        """Get a parameter by name"""
        for param in self.parameters:
            if param.name == name:
                return param
        return None


@dataclass
class ToolCall:
    """Represents a tool call from the LLM"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResult:
    """Represents the result of a tool call"""
    tool_call_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None


@dataclass
class LLMResponse:
    """Unified response from LLM"""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None
    raw_response: Any = None


class UnifiedLLMInterface:
    """Unified interface for interacting with different LLM providers"""
    
    # Model to provider mapping
    MODEL_PROVIDERS = {
        # OpenAI models
        "gpt-3.5-turbo": LLMProvider.OPENAI,
        "gpt-4": LLMProvider.OPENAI,
        "gpt-4-turbo": LLMProvider.OPENAI,
        "gpt-4o": LLMProvider.OPENAI,
        "gpt-4.1": LLMProvider.OPENAI,
        
        # Anthropic models
        "claude-3-haiku-20240307": LLMProvider.ANTHROPIC,
        "claude-3-sonnet-20240229": LLMProvider.ANTHROPIC,
        "claude-3-opus-20240229": LLMProvider.ANTHROPIC,
        "claude-3-5-sonnet-20241022": LLMProvider.ANTHROPIC,
        "claude-sonnet-4-20250514": LLMProvider.ANTHROPIC,
        
        # Gemini models
        "gemini-pro": LLMProvider.GEMINI,
        "gemini-2.5-flash": LLMProvider.GEMINI,
        "gemini-1.5-pro": LLMProvider.GEMINI,
        "gemini-1.5-flash": LLMProvider.GEMINI,
    }
    
    def __init__(self, api_keys: Optional[Dict[str, str]] = None):
        self._tools: List[UnifiedTool] = []
        self._clients = {}
        self._api_keys = api_keys or {}
        
        # Initialize clients
        self._init_clients()
    
    def _init_clients(self):
        """Initialize all available clients"""
        # OpenAI
        try:
            from openai import OpenAI
            api_key = self._api_keys.get('openai') or os.getenv('OPENAI_API_KEY')
            if api_key:
                self._clients[LLMProvider.OPENAI] = OpenAI(api_key=api_key)
        except ImportError:
            pass
        
        # Anthropic
        try:
            from anthropic import Anthropic
            api_key = self._api_keys.get('anthropic') or os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                self._clients[LLMProvider.ANTHROPIC] = Anthropic(api_key=api_key)
        except ImportError:
            pass
        
        # Gemini
        try:
            from google import genai
            api_key = self._api_keys.get('gemini') or os.getenv('GEMINI_API_KEY')
            if api_key:
                self._clients[LLMProvider.GEMINI] = genai.Client(api_key=api_key)
        except ImportError:
            pass
    
    def _get_provider_from_model(self, model: str) -> LLMProvider:
        """Determine provider from model name"""
        return self.MODEL_PROVIDERS.get(model, LLMProvider.OPENAI)
    
    def add_tool(self, tool: UnifiedTool):
        """Add a tool to the interface"""
        self._tools.append(tool)
    
    def get_tools(self) -> List[UnifiedTool]:
        """Get all registered tools"""
        return self._tools.copy()
    
    def create(self, 
               model: str,
               messages: List[Dict[str, Any]],
               max_tokens: Optional[int] = None,
               temperature: Optional[float] = None,
               system: Optional[str] = None,
               tools: Optional[List[UnifiedTool]] = None,
               **kwargs) -> LLMResponse:
        """
        Unified create method that works with all providers
        
        Args:
            model: Model name (determines provider automatically)
            messages: List of message dictionaries
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            system: System prompt
            tools: List of tools to make available
            **kwargs: Additional provider-specific parameters
        
        Returns:
            LLMResponse: Unified response object
        """
        provider = self._get_provider_from_model(model)
        
        if provider not in self._clients:
            raise ValueError(f"No client available for provider {provider.value}. Check API key configuration.")
        
        # Set tools if provided
        if tools:
            self._tools = tools
        
        if provider == LLMProvider.OPENAI:
            return self._create_openai(model, messages, max_tokens, temperature, system, **kwargs)
        elif provider == LLMProvider.ANTHROPIC:
            return self._create_anthropic(model, messages, max_tokens, temperature, system, **kwargs)
        elif provider == LLMProvider.GEMINI:
            return self._create_gemini(model, messages, max_tokens, temperature, system, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    def _create_openai(self, model: str, messages: List[Dict[str, Any]], 
                      max_tokens: Optional[int], temperature: Optional[float], 
                      system: Optional[str], **kwargs) -> LLMResponse:
        """Create OpenAI completion"""
        client = self._clients[LLMProvider.OPENAI]
        
        # Format messages
        formatted_messages = []
        if system:
            formatted_messages.append({"role": "system", "content": system})
        formatted_messages.extend(messages)
        
        # Prepare request parameters
        request_params = {
            "model": model,
            "messages": formatted_messages,
        }
        
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if temperature is not None:
            request_params["temperature"] = temperature
        if self._tools:
            request_params["tools"] = self._get_openai_tools_schema()
        
        # Add any additional kwargs
        request_params.update(kwargs)
        
        # Make API call
        response = client.chat.completions.create(**request_params)
        
        # Parse response
        content = response.choices[0].message.content or ""
        tool_calls = self._parse_openai_tool_calls(response)
        
        usage = None
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            raw_response=response
        )
    
    def _create_anthropic(self, model: str, messages: List[Dict[str, Any]], 
                         max_tokens: Optional[int], temperature: Optional[float], 
                         system: Optional[str], **kwargs) -> LLMResponse:
        """Create Anthropic completion"""
        client = self._clients[LLMProvider.ANTHROPIC]
        
        # Prepare request parameters
        request_params = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or 4096,
        }
        
        if system:
            request_params["system"] = system
        if temperature is not None:
            request_params["temperature"] = temperature
        if self._tools:
            request_params["tools"] = self._get_anthropic_tools_schema()
        
        # Add any additional kwargs
        request_params.update(kwargs)
        
        # Make API call
        response = client.messages.create(**request_params)
        
        # Parse response
        content = ""
        tool_calls = []
        
        for block in response.content:
            if hasattr(block, 'type'):
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input)
                    ))
        
        usage = None
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            }
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=response.stop_reason,
            raw_response=response
        )
    
    def _create_gemini(self, model: str, messages: List[Dict[str, Any]], 
                      max_tokens: Optional[int], temperature: Optional[float], 
                      system: Optional[str], **kwargs) -> LLMResponse:
        """Create Gemini completion"""
        client = self._clients[LLMProvider.GEMINI]
        
        # Convert messages to Gemini format
        from google.genai import types as gemini_types
        
        gemini_contents = []
        for message in messages:
            if message['role'] == 'user':
                content_text = message['content']
                if system and len(gemini_contents) == 0:
                    content_text = f"{system}\n\n{content_text}"
                
                gemini_contents.append(gemini_types.Content(
                    role='user',
                    parts=[gemini_types.Part.from_text(text=content_text)]
                ))
            elif message['role'] == 'assistant':
                gemini_contents.append(gemini_types.Content(
                    role='model',
                    parts=[gemini_types.Part.from_text(text=message['content'])]
                ))
        
        # Prepare request parameters
        config_params = {}
        if temperature is not None:
            config_params["temperature"] = temperature
        if max_tokens:
            config_params["max_output_tokens"] = max_tokens
        if self._tools:
            config_params["tools"] = self._get_gemini_tools_schema()
        
        config = gemini_types.GenerateContentConfig(**config_params)
        
        # Make API call
        response = client.models.generate_content(
            model=model,
            contents=gemini_contents,
            config=config
        )
        
        # Parse response
        content = ""
        tool_calls = []
        
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    content += part.text
                elif hasattr(part, 'function_call') and part.function_call:
                    tool_calls.append(ToolCall(
                        id=part.function_call.name,
                        name=part.function_call.name,
                        arguments=dict(part.function_call.args) if part.function_call.args else {}
                    ))
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=None,  # Gemini doesn't provide usage in same format
            finish_reason=None,
            raw_response=response
        )
    
    def _parameter_to_json_schema(self, param: ToolParameter) -> Dict[str, Any]:
        """Convert a ToolParameter to JSON Schema format"""
        schema = {
            "type": param.type,
            "description": param.description
        }
        
        if param.default is not None:
            schema["default"] = param.default
        
        if param.enum:
            schema["enum"] = param.enum
        
        if param.type == "object" and param.properties:
            schema["properties"] = {}
            required = []
            for prop_name, prop_param in param.properties.items():
                schema["properties"][prop_name] = self._parameter_to_json_schema(prop_param)
                if prop_param.required:
                    required.append(prop_name)
            if required:
                schema["required"] = required
        
        return schema
    
    def _tool_to_json_schema(self, tool: UnifiedTool) -> Dict[str, Any]:
        """Convert a UnifiedTool to JSON Schema format"""
        properties = {}
        required = []
        
        for param in tool.parameters:
            properties[param.name] = self._parameter_to_json_schema(param)
            if param.required:
                required.append(param.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        }
    
    def get_provider_tools_schema(self, provider: LLMProvider) -> Union[List[Dict], List[Any]]:
        """Get tools schema formatted for the specified provider"""
        if provider == LLMProvider.OPENAI:
            return self._get_openai_tools_schema()
        elif provider == LLMProvider.ANTHROPIC:
            return self._get_anthropic_tools_schema()
        elif provider == LLMProvider.GEMINI:
            return self._get_gemini_tools_schema()
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    def _get_openai_tools_schema(self) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tools schema"""
        tools = []
        for tool in self._tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": self._tool_to_json_schema(tool)
                }
            })
        return tools
    
    def _get_anthropic_tools_schema(self) -> List[Dict[str, Any]]:
        """Get Anthropic-compatible tools schema"""
        tools = []
        for tool in self._tools:
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": self._tool_to_json_schema(tool)
            })
        return tools
    
    def _get_gemini_tools_schema(self) -> List[Any]:
        """Get Gemini-compatible tools schema"""
        try:
            from google.genai import types as gemini_types
            
            function_declarations = []
            for tool in self._tools:
                # Convert parameters to Gemini Schema format
                properties = {}
                required = []
                
                for param in tool.parameters:
                    gemini_type = gemini_types.Type.STRING
                    if param.type == "integer":
                        gemini_type = gemini_types.Type.INTEGER
                    elif param.type == "boolean":
                        gemini_type = gemini_types.Type.BOOLEAN
                    elif param.type == "array":
                        gemini_type = gemini_types.Type.ARRAY
                    elif param.type == "object":
                        gemini_type = gemini_types.Type.OBJECT
                    
                    properties[param.name] = gemini_types.Schema(
                        type=gemini_type,
                        description=param.description
                    )
                    
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
                function_declarations.append(function_decl)
            
            return [gemini_types.Tool(function_declarations=function_declarations)]
        except ImportError:
            # Fallback to dict format if Gemini not available
            tools = []
            for tool in self._tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": self._tool_to_json_schema(tool)
                })
            return tools
    
    def parse_tool_calls(self, response: Any, provider: LLMProvider) -> List[ToolCall]:
        """Parse tool calls from provider response"""
        if provider == LLMProvider.OPENAI:
            return self._parse_openai_tool_calls(response)
        elif provider == LLMProvider.ANTHROPIC:
            return self._parse_anthropic_tool_calls(response)
        elif provider == LLMProvider.GEMINI:
            return self._parse_gemini_tool_calls(response)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    def _parse_openai_tool_calls(self, response: Any) -> List[ToolCall]:
        """Parse OpenAI tool calls"""
        tool_calls = []
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'tool_calls'):
                for tc in choice.message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments)
                    ))
        return tool_calls
    
    def _parse_anthropic_tool_calls(self, response: Any) -> List[ToolCall]:
        """Parse Anthropic tool calls"""
        tool_calls = []
        if hasattr(response, 'content'):
            for block in response.content:
                if hasattr(block, 'type') and block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input)
                    ))
        return tool_calls
    
    def _parse_gemini_tool_calls(self, response: Any) -> List[ToolCall]:
        """Parse Gemini tool calls"""
        tool_calls = []
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        tool_calls.append(ToolCall(
                            id=part.function_call.name,  # Gemini doesn't have separate IDs
                            name=part.function_call.name,
                            arguments=dict(part.function_call.args) if part.function_call.args else {}
                        ))
        return tool_calls
    
    def format_tool_results(self, results: List[ToolResult]) -> Any:
        """Format tool results for the provider"""
        if self.provider == LLMProvider.OPENAI:
            return self._format_openai_tool_results(results)
        elif self.provider == LLMProvider.ANTHROPIC:
            return self._format_anthropic_tool_results(results)
        elif self.provider == LLMProvider.GEMINI:
            return self._format_gemini_tool_results(results)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _format_openai_tool_results(self, results: List[ToolResult]) -> List[Dict[str, Any]]:
        """Format tool results for OpenAI"""
        formatted_results = []
        for result in results:
            formatted_results.append({
                "tool_call_id": result.tool_call_id,
                "role": "tool",
                "content": json.dumps({
                    "success": result.success,
                    "result": result.result,
                    "error": result.error
                })
            })
        return formatted_results
    
    def _format_anthropic_tool_results(self, results: List[ToolResult]) -> List[Dict[str, Any]]:
        """Format tool results for Anthropic"""
        formatted_results = []
        for result in results:
            formatted_results.append({
                "type": "tool_result",
                "tool_use_id": result.tool_call_id,
                "content": json.dumps({
                    "success": result.success,
                    "result": result.result,
                    "error": result.error
                })
            })
        return formatted_results
    
    def _format_gemini_tool_results(self, results: List[ToolResult]) -> List[Dict[str, Any]]:
        """Format tool results for Gemini"""
        formatted_results = []
        for result in results:
            formatted_results.append({
                "name": result.tool_call_id,
                "response": {
                    "success": result.success,
                    "result": result.result,
                    "error": result.error
                }
            })
        return formatted_results


def create_example_tools() -> List[UnifiedTool]:
    """Create example tools to demonstrate the interface"""
    tools = []
    
    # File reading tool
    tools.append(UnifiedTool(
        name="read_file",
        description="Read contents of a file",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the file to read",
                required=True
            ),
            ToolParameter(
                name="offset",
                type="integer",
                description="Optional starting line number",
                required=False
            ),
            ToolParameter(
                name="limit",
                type="integer", 
                description="Optional maximum number of lines to read",
                required=False
            )
        ]
    ))
    
    # Weather tool (like OpenAI example)
    tools.append(UnifiedTool(
        name="get_weather",
        description="Get current temperature for a given location",
        parameters=[
            ToolParameter(
                name="location",
                type="string",
                description="City and country e.g. Bogotá, Colombia",
                required=True
            ),
            ToolParameter(
                name="units",
                type="string",
                description="Temperature units",
                required=False,
                enum=["celsius", "fahrenheit"],
                default="celsius"
            )
        ]
    ))
    
    return tools


if __name__ == "__main__":
    # Example usage
    llm = UnifiedLLMInterface()
    
    # Add tools
    for tool in create_example_tools():
        llm.add_tool(tool)
    
    # Example: Use OpenAI
    try:
        response = llm.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "What's the weather like in Paris?"}],
            max_tokens=100,
            temperature=0.7,
            tools=create_example_tools()
        )
        print("OpenAI Response:")
        print(f"Content: {response.content}")
        print(f"Tool calls: {response.tool_calls}")
    except Exception as e:
        print(f"OpenAI error: {e}")
    
    # Example: Use Claude
    try:
        response = llm.create(
            model="claude-3-sonnet-20240229",
            messages=[{"role": "user", "content": "Read the file 'example.txt'"}],
            max_tokens=1000,
            temperature=0,
            system="You are a helpful assistant."
        )
        print("\nClaude Response:")
        print(f"Content: {response.content}")
        print(f"Tool calls: {response.tool_calls}")
    except Exception as e:
        print(f"Claude error: {e}")
    
    # Example: Use Gemini
    try:
        response = llm.create(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "Hello, how are you?"}],
            max_tokens=50,
            temperature=0.5
        )
        print("\nGemini Response:")
        print(f"Content: {response.content}")
        print(f"Tool calls: {response.tool_calls}")
    except Exception as e:
        print(f"Gemini error: {e}")
    
    # Show schema examples
    print("\n" + "="*50)
    print("SCHEMA EXAMPLES")
    print("="*50)
    
    # Get OpenAI-compatible schema
    openai_schema = llm.get_provider_tools_schema(LLMProvider.OPENAI)
    print("\nOpenAI Schema:")
    print(json.dumps(openai_schema, indent=2))
    
    # Get Anthropic-compatible schema
    anthropic_schema = llm.get_provider_tools_schema(LLMProvider.ANTHROPIC)
    print("\nAnthropic Schema:")
    print(json.dumps(anthropic_schema, indent=2))