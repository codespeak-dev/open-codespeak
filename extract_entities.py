import logging
from colors import Colors
from data_serializer import json_file
from phase_manager import State, Phase, Context
from with_step import with_step
from fileutils import format_file_content, load_prompt_template
from entity_extractor import (Entity, to_entities, ENTITY_TOOLS_SCHEMA, EntityExtractor)


def extract_entities(context: Context, spec: str, existing_entities=None, spec_diff=None) -> list[dict]:
    """
    Uses Claude to extract a list of Django models and their fields from the prompt.
    Returns a list of Entity objects with fields and relationships.
    """

    with with_step("Figuring out the data model..."):
        # Adds line numbers to the spec, to make it easier to understand the diff
        spec, _ = format_file_content(spec, offset=None, limit=None, truncate_line=None)
        user_prompt = load_prompt_template("extract_entities", existing_entities=existing_entities, spec_diff=spec_diff, spec=spec)

        extractor = EntityExtractor(context.anthropic_client, model="claude-3-7-sonnet-latest")
        entities_data = extractor.extract_entities(
            spec=spec,
            existing_entities=existing_entities,
            spec_diff=spec_diff,
            user_prompt=user_prompt
        )

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

        entities_data = extract_entities(context, spec, existing_entities=existing_entities, spec_diff=spec_diff)

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
