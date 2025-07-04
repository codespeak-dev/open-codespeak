import logging
from colors import Colors
from data_serializer import json_file
from phase_manager import State, Phase, Context
from with_step import with_step
from pydantic import BaseModel
from anthropic.types import ToolParam
from fileutils import format_file_content, load_template as load_template_jinja

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

def to_entities(raw_data):
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


def extract_models_and_fields(spec: str, context: Context, existing_entities=None, spec_diff=None) -> list[dict]:
    """
    Uses Claude to extract a list of Django models and their fields from the prompt.
    Returns a list of Entity objects with fields and relationships.
    """

    with with_step("Figuring out the data model..."):
        system_prompt = "You are an expert Django developer and an excellent data modeler."

        # Adds line numbers to the spec, to make it easier to understand the diff
        spec, _ = format_file_content(spec, offset=None, limit=None, truncate_line=None)
        user_prompt = load_template_jinja("prompts/extract_entities.j2", existing_entities=existing_entities, spec_diff=spec_diff, spec=spec)

        message = context.anthropic_client.create(
            model="claude-3-7-sonnet-latest",
            max_tokens=10000,
            temperature=1,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            thinking={
                "type": "enabled",
                "budget_tokens": 4000
            },
            tools=ENTITY_TOOLS_SCHEMA
        )

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

def display_entities(entities: list[Entity], logger):
    """Display entities in a formatted way"""
    lines = []
    for entity in entities:
        lines.append(f"  - {Colors.BOLD}{Colors.BRIGHT_GREEN}{entity.name}{Colors.END}")
        for rel in entity.relationships:
            lines.append(f"      {Colors.BRIGHT_MAGENTA}{rel.name}{Colors.END}: {rel.type} -> {Colors.BRIGHT_GREEN}{rel.related_to}{Colors.END}")
        for field in entity.fields:
            lines.append(f"      {Colors.BRIGHT_YELLOW}{field.name}{Colors.END}: {field.type}")
    logger.info(f"Entities extracted: " + "\n".join(lines))

class ExtractEntities(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)
    description = "Extract data entities from the specification"

    def run(self, state: State, context: Context) -> dict:
        spec = state["spec"]
        existing_entities = state.get("entities", [])
        spec_diff = state.get("spec_diff")

        entities_data = extract_models_and_fields(spec, context, existing_entities=existing_entities, spec_diff=spec_diff)

        if len(entities_data) > 0:
            display_entities(to_entities(entities_data), self.logger)
        else:
            self.logger.info("No entities extracted")

        return {
            "entities": entities_data
        }

    def get_state_schema_entries(self) -> dict[str, dict]:
        return {
            "entities": json_file("entities.json")
        }
