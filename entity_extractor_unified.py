import logging
from typing import List, Dict, Optional, Any, Protocol, Union
from pydantic import BaseModel
from unified_llm_interface import UnifiedLLMInterface, UnifiedTool, ToolParameter, LLMResponse, ToolCall

try:
    from llm_cache.anthropic_cached import CachedAnthropic
    from anthropic.types import ToolParam
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

class EntityField(BaseModel):
    name: str
    type: str


class EntityRelationship(BaseModel):
    name: str
    type: str
    related_to: str
    related_name: str


class Entity(BaseModel):
    name: str
    fields: list[EntityField]
    relationships: list[EntityRelationship] = []


def to_entities(raw_data: list[dict]) -> list[Entity]:
    return [Entity(**item) for item in raw_data]


class LLMInterface(Protocol):
    """Protocol for LLM interface - allows for dependency injection"""
    
    def create(self, 
               model: str,
               messages: List[Dict[str, Any]],
               max_tokens: Optional[int] = None,
               temperature: Optional[float] = None,
               system: Optional[str] = None,
               tools: Optional[List[UnifiedTool]] = None,
               **kwargs) -> LLMResponse:
        """Create a completion with the LLM"""
        ...


def create_entity_extraction_tool() -> UnifiedTool:
    """Create the entity extraction tool in unified format"""
    return UnifiedTool(
        name="entities",
        description="Extract Django models and their fields from the specification",
        parameters=[
            ToolParameter(
                name="entities",
                type="array",
                description="Array of Django models with their fields and relationships",
                required=True,
                properties={
                    "name": ToolParameter(
                        name="name",
                        type="string",
                        description="The Django model name",
                        required=True
                    ),
                    "fields": ToolParameter(
                        name="fields",
                        type="array",
                        description="Array of field objects with name and type",
                        required=True,
                        properties={
                            "name": ToolParameter(
                                name="name",
                                type="string",
                                description="Field name",
                                required=True
                            ),
                            "type": ToolParameter(
                                name="type",
                                type="string",
                                description="Django field type, e.g. 'CharField(max_length=100)'",
                                required=True
                            )
                        }
                    ),
                    "relationships": ToolParameter(
                        name="relationships",
                        type="array",
                        description="Array of relationship objects",
                        required=False,
                        properties={
                            "name": ToolParameter(
                                name="name",
                                type="string",
                                description="Relationship field name",
                                required=True
                            ),
                            "type": ToolParameter(
                                name="type",
                                type="string",
                                description="Relationship type like 'ForeignKey', 'ManyToManyField', 'OneToOneField'",
                                required=True
                            ),
                            "related_to": ToolParameter(
                                name="related_to",
                                type="string",
                                description="The related model name, e.g. 'User' for author field",
                                required=True
                            ),
                            "related_name": ToolParameter(
                                name="related_name",
                                type="string",
                                description="The related name for reverse lookups, e.g. 'posts' for author->posts relationship",
                                required=True
                            )
                        }
                    )
                }
            )
        ]
    )


class EntityExtractor:
    def __init__(self, 
                 llm_interface: LLMInterface, 
                 model: str = "claude-3-sonnet-20240229"):
        """
        Initialize with any LLM interface that implements the protocol
        
        Args:
            llm_interface: Any object implementing LLMInterface protocol
            model: Model name to use (can be from any provider)
        """
        self.llm_interface = llm_interface
        self.model = model
        self.extraction_tool = create_entity_extraction_tool()
    
    def extract_entities(
        self,
        spec: str,
        user_prompt: str,
        existing_entities: Optional[List[Dict]] = None,
        spec_diff: Optional[str] = None,
    ) -> List[Dict]:
        """Extract entities using the unified LLM interface"""
        system_prompt = "You are an expert Django developer and an excellent data modeler."

        response = self.llm_interface.create(
            model=self.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[self.extraction_tool],
            max_tokens=10000,
            temperature=1
        )

        return self.extract_entities_from_response(response)

    def display_entities(self, entities: list[Entity]) -> None:
        """Display entities in a simple format"""
        print("Extracted Entities:")
        for entity in entities:
            print(f"  - {entity.name}")
            for rel in entity.relationships:
                print(f"      {rel.name}: {rel.type} -> {rel.related_to}")
            for field in entity.fields:
                print(f"      {field.name}: {field.type}")

    def extract_entities_from_response(self, response: LLMResponse) -> list[dict]:
        """Extract entities from unified LLM response"""
        entities_data = []

        # Look for tool calls in the response
        for tool_call in response.tool_calls:
            if tool_call.name == "entities":
                entities_data = tool_call.arguments.get("entities", [])
                break

        return entities_data


# Example usage showing flexibility
if __name__ == "__main__":
    # Can use with any provider
    llm = UnifiedLLMInterface()
    
    # Use with Claude
    extractor_claude = EntityExtractor(llm, model="claude-3-sonnet-20240229")
    
    # Use with OpenAI
    extractor_openai = EntityExtractor(llm, model="gpt-4")
    
    # Use with Gemini
    extractor_gemini = EntityExtractor(llm, model="gemini-2.5-flash")
    
    # All work the same way
    spec = "Create a blog system with users, posts, and comments"
    prompt = f"Extract Django models from this specification: {spec}"
    
    try:
        entities = extractor_claude.extract_entities(spec, prompt)
        print(f"Claude extracted {len(entities)} entities")
    except Exception as e:
        print(f"Claude error: {e}")
    
    try:
        entities = extractor_openai.extract_entities(spec, prompt)
        print(f"OpenAI extracted {len(entities)} entities")
    except Exception as e:
        print(f"OpenAI error: {e}")