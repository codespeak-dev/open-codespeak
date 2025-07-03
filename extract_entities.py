import json
from colors import Colors
from data_serializer import json_file
import llm_cache
from phase_manager import State, Phase, Context
from with_step import with_streaming_step
from pydantic import BaseModel
from typing import Dict, List, Optional
from anthropic.types import ToolParam

SYSTEM_PROMPT = """
You are an expert Django developer and an excellent data modeler. Given a user prompt, extract a list of Django models and their fields.

IMPORTANT: you should only extract entities that are actually storing the data in the database. It's perfectly fine for a specification not to have any entities.

IMPORTANT: If there's an intermediate model that connects two other models (like Appointment with Patient and Doctor, or like LineItem with Order and Product),
do NOT create direct ManyToManyField relationships between the connected models. 
The intermediate model's ForeignKey relationships are sufficient to represent the many-to-many connection.
"""

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
    fields: List[EntityField]
    relationships: List[EntityRelationship] = []

def to_entities(raw_data):
    # Convert tool response format to Entity objects
    return [Entity(**item) for item in raw_data]

# Tool definitions constant
ENTITY_TOOLS_SCHEMA: list[ToolParam] = [
    ToolParam(
        name="entities",
        description="Extract Django models and their fields from the specification",
        input_schema={
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The Django model name"
                            },
                            "fields": {
                                "type": "array",
                                "description": "Array of field objects with name and type",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "Field name"
                                        },
                                        "type": {
                                            "type": "string",
                                            "description": "Django field type, e.g. 'CharField(max_length=100)'"
                                        }
                                    },
                                    "required": ["name", "type"]
                                }
                            },
                            "relationships": {
                                "type": "array",
                                "description": "Array of relationship objects",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "Relationship field name"
                                        },
                                        "type": {
                                            "type": "string",
                                            "description": "Relationship type like 'ForeignKey', 'ManyToManyField', 'OneToOneField'"
                                        },
                                        "related_to": {
                                            "type": "string",
                                            "description": "The related model name, e.g. 'User' for author field"
                                        },
                                        "related_name": {
                                            "type": "string",
                                            "description": "The related name for reverse lookups, e.g. 'posts' for author->posts relationship"
                                        }
                                    },
                                    "required": ["name", "type", "related_to", "related_name"]
                                }
                            }
                        },
                        "required": ["name", "fields"]
                    }
                }
            },
            "required": ["entities"]
        }
    )
]


def extract_models_and_fields(prompt: str) -> List[dict]:
    """
    Uses Claude to extract a list of Django models and their fields from the prompt.
    Returns a list of Entity objects with fields and relationships.
    """
    client = llm_cache.Anthropic()

    with with_streaming_step("Figuring out the data model...") as (input_tokens, output_tokens):
        input_tokens[0] = len((SYSTEM_PROMPT + prompt).split())

        message = client.messages.create(
            model="claude-3-7-sonnet-latest",
            max_tokens=10000,
            temperature=1,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            thinking={
                "type": "enabled",
                "budget_tokens": 4000
            },
            tools=ENTITY_TOOLS_SCHEMA
        )

        # Calculate output tokens
        if hasattr(message, 'content'):
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == 'text':
                    output_tokens[0] += len(content_block.text.split())

        # Extract entities from tool use
        entities_data = []
        if hasattr(message, 'content'):
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == 'tool_use':
                    if hasattr(content_block, 'name') and content_block.name == 'entities':
                        if hasattr(content_block, 'input') and isinstance(content_block.input, dict):
                            entities_data = content_block.input.get('entities', [])
                        break

        return entities_data

def display_entities(entities: List[Entity]):
    """Display entities in a formatted way"""
    print("Entities extracted:")
    for entity in entities:
        print(f"  - {Colors.BOLD}{Colors.BRIGHT_GREEN}{entity.name}{Colors.END}")
        for rel in entity.relationships:
            print(f"      {Colors.BRIGHT_MAGENTA}{rel.name}{Colors.END}: {rel.type} -> {Colors.BRIGHT_GREEN}{rel.related_to}{Colors.END}")
        for field in entity.fields:
            print(f"      {Colors.BRIGHT_YELLOW}{field.name}{Colors.END}: {field.type}")

class ExtractEntities(Phase):
    description = "Extract data entities from the specification"

    def run(self, state: State, context: Context) -> dict:
        spec = state["spec"]

        entities_data = extract_models_and_fields(spec)

        display_entities(to_entities(entities_data))

        return {
            "entities": entities_data
        }

    def get_state_schema_entries(self) -> Dict[str, dict]:
        return {
            "entities": json_file("entities.json")
        }
