import logging
from pydantic import BaseModel
from llm_cache.anthropic_cached import CachedAnthropic
from tool_definitions import (
    Tool, string_param, array_param, object_param, to_anthropic
)

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


ENTITY_EXTRACTION_TOOL = Tool(
    name="entities",
    description="Extract Django models and their fields from the specification",
    parameters=[
        array_param(
            name="entities",
            description="Array of Django models with their fields and relationships",
            required=True,
            items=object_param(
                name="entity",
                description="Django model definition",
                properties={
                    "name": string_param("name", "The Django model name", required=True),
                    "fields": array_param(
                        name="fields",
                        description="Array of field objects with name and type",
                        required=True,
                        items=object_param(
                            name="field",
                            description="Django field definition",
                            properties={
                                "name": string_param("name", "Field name", required=True),
                                "type": string_param("type", "Django field type, e.g. 'CharField(max_length=100)'", required=True)
                            }
                        )
                    ),
                    "relationships": array_param(
                        name="relationships",
                        description="Array of relationship objects",
                        required=False,
                        items=object_param(
                            name="relationship",
                            description="Django relationship definition",
                            properties={
                                "name": string_param("name", "Relationship field name", required=True),
                                "type": string_param("type", "Relationship type like 'ForeignKey', 'ManyToManyField', 'OneToOneField'", required=True),
                                "related_to": string_param("related_to", "The related model name, e.g. 'User' for author field", required=True),
                                "related_name": string_param("related_name", "The related name for reverse lookups, e.g. 'posts' for author->posts relationship", required=True)
                            }
                        )
                    )
                }
            )
        )
    ]
)


class EntityExtractor:
    def __init__(self, client: CachedAnthropic, model: str = "claude-3-sonnet-20240229"):
        self.client = client
        self.model = model
    
    def extract_entities(self, user_prompt: str,) -> list[dict]:
        system_prompt = "You are an expert Django developer and an excellent data modeler."

        message = self.client.create(
            model=self.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[to_anthropic(ENTITY_EXTRACTION_TOOL)],
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

