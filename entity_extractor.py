import logging
from typing import List, Dict, Optional, Any, Protocol
from pydantic import BaseModel
from anthropic.types import ToolParam
from llm_cache.anthropic_cached import CachedAnthropic

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


class EntityExtractor:
    def __init__(self, client: CachedAnthropic, model: str = "claude-3-sonnet-20240229"):
        self.client = client
        self.model = model
    
    def extract_entities(
        self,
        spec: str,
        existing_entities: Optional[List[Dict]] = None,
        spec_diff: Optional[str] = None,
        user_prompt: Optional[str] = None
    ) -> List[Dict]:
        system_prompt = "You are an expert Django developer and an excellent data modeler."

        if user_prompt is None:
            user_prompt = f"""
Extract Django models and their fields from the following specification:

{spec}

Please analyze the specification and extract all the data models (Django models) that would be needed.
For each model, identify:
1. The model name
2. All fields with their appropriate Django field types
3. Any relationships between models

{"Previous entities for context: " + str(existing_entities) if existing_entities else ""}
{"Recent changes to specification: " + spec_diff if spec_diff else ""}

Use the entities tool to return the extracted models in the required format.
"""

        message = self.client.create(
            model=self.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=ENTITY_TOOLS_SCHEMA,
            max_tokens=10000,
            temperature=1
        )

        return self.extract_entities_from_response(message)


    def display_entities(self, entities: list[Entity]) -> None:
        """Display entities in a simple format"""
        print("Extracted Entities:")
        for entity in entities:
            print(f"  - {entity.name}")
            for rel in entity.relationships:
                print(f"      {rel.name}: {rel.type} -> {rel.related_to}")
            for field in entity.fields:
                print(f"      {field.name}: {field.type}")


    def extract_entities_from_response(self, message) -> list[dict]:
        """Extract entities from LLM response"""
        entities_data = []

        if hasattr(message, 'content'):
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == 'tool_use':
                    if hasattr(content_block, 'name') and content_block.name == 'entities':
                        if hasattr(content_block, 'input') and isinstance(content_block.input, dict):
                            entities_data = content_block.input.get('entities', [])
                        break

        return entities_data

