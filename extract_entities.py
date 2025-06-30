import json
import sys
import anthropic
import inquirer
from colors import Colors
from data_serializer import json_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step
from pydantic import BaseModel
from typing import Dict, List, Optional, Tuple

class EntityField(BaseModel):
    name: str
    field_type: str
    related_to: Optional[str] = None
    relationship_type: Optional[str] = None

class Entity(BaseModel):
    name: str
    fields: Dict[str, str]
    relationships: Dict[str, Dict[str, str]] = {}


def slice_dict(d, *keys):
    return {k: v for k, v in d.items() if k in keys}

def to_entities(raw_data):
    # LLM might send extra fields, so we need to filter them out
    # so far this seems more reliable that trying to prompt with with "never return anything other than the fields we ask for"
    def filter_item(item):
        filtered = slice_dict(item, 'name', 'fields', 'relationships')
        if 'relationships' in filtered and isinstance(filtered['relationships'], dict):
            filtered['relationships'] = {
                rel_name: slice_dict(rel_info, 'type', 'related_to', 'related_name') 
                if isinstance(rel_info, dict) else rel_info
                for rel_name, rel_info in filtered['relationships'].items()
            }
        return filtered

    return [Entity(**filter_item(item)) for item in raw_data]

def extract_models_and_fields(prompt: str) -> List[Entity]:
    """
    Uses Claude to extract a list of Django models and their fields from the prompt.
    Returns a list of Entity objects with fields and relationships.
    """
    client = anthropic.Anthropic()
    system_prompt = (
        "You are an expert Django developer and an excellent data modeler. Given a user prompt, extract a list of Django models and their fields. "
        "Return a JSON array of objects, each with:"
        "- 'name' (model name)"
        "- 'fields' (object mapping field names to Django field types, e.g. 'CharField(max_length=100)')"
        "- 'relationships' (object mapping field names to relationship info with 'type', 'related_to', 'related_name' keys)"
        "For relationships, use types like 'ForeignKey', 'ManyToManyField', 'OneToOneField'."
        "IMPORTANT: If there's an intermediate model that connects two other models (like Appointment with Patient and Doctor, or like LineItem with Order and Product), "
        "do NOT create direct ManyToManyField relationships between the connected models. "
        "The intermediate model's ForeignKey relationships are sufficient to represent the many-to-many connection."
        "Example: {\"name\": \"Post\", \"fields\": {\"title\": \"CharField(max_length=100)\"}, \"relationships\": {\"author\": {\"type\": \"ForeignKey\", \"related_to\": \"User\", \"related_name\": \"posts\"}}}"
        "Do not include any explanation, only valid JSON."
    )

    with with_streaming_step("Figuring out the data model...") as (input_tokens, output_tokens):
        response_text = ""
        # Count input tokens from system prompt and user prompt
        input_tokens[0] = len((system_prompt + prompt).split())

        with client.messages.stream(
            model="claude-3-7-sonnet-latest",
            max_tokens=10000,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                output_tokens[0] += len(text.split())

    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError as e:
        print(f"{Colors.BRIGHT_RED}Error: Failed to parse JSON response from Claude: {e}{Colors.END}")
        print(f"{Colors.BRIGHT_YELLOW}Raw response: {response_text}{Colors.END}")
        raise

def refine_entities(original_prompt: str, entities: dict, feedback: str) -> dict:
    """
    Use Claude to refine entities based on user feedback.
    """
    client = anthropic.Anthropic()

    # Convert entities to JSON for the prompt
    entities_json = json.dumps(entities, indent=2)

    system_prompt = (
        "You are an expert Django developer. Given the original user prompt, current entities, and user feedback, "
        "modify the entities accordingly. Return a JSON array of objects with the same structure: "
        "- 'name' (model name)"
        "- 'fields' (object mapping field names to Django field types)"
        "- 'relationships' (object mapping field names to relationship info with 'type' and 'related_to' keys)"
        "Only return the JSON array, no explanation."
    )

    user_message = f"""Original prompt:
{original_prompt}

Current entities:
{entities_json}

User feedback:
{feedback}

Please modify the entities based on the feedback."""

    with with_streaming_step("Refining entities based on feedback...") as (input_tokens, output_tokens):
        response_text = ""
        # Count input tokens from system prompt and user message
        input_tokens[0] = len((system_prompt + user_message).split())

        with client.messages.stream(
            model="claude-3-5-sonnet-latest",
            max_tokens=8192,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                output_tokens[0] += len(text.split())

    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError as e:
        print(f"{Colors.BRIGHT_RED}Error: Failed to parse JSON response from Claude during refinement: {e}{Colors.END}")
        print(f"{Colors.BRIGHT_YELLOW}Raw response: {response_text}{Colors.END}")
        raise

def display_entities(entities: List[Entity]):
    """Display entities in a formatted way"""
    print("Entities extracted:")
    for entity in entities:
        print(f"  - {Colors.BOLD}{Colors.BRIGHT_GREEN}{entity.name}{Colors.END}")
        for rel_field, rel_info in entity.relationships.items():
            print(f"      {Colors.BRIGHT_MAGENTA}{rel_field}{Colors.END}: {rel_info['type']} -> {Colors.BRIGHT_GREEN}{rel_info['related_to']}{Colors.END}")
        for field, ftype in entity.fields.items():
            print(f"      {Colors.BRIGHT_YELLOW}{field}{Colors.END}: {ftype}")

class ExtractEntities(Phase):
    def run(self, state: State, context: Context = None) -> dict:
        spec = state["spec"]

        entities = extract_models_and_fields(spec)

        return {
            "entities": entities
        }

    def get_state_schema_entries(self) -> Dict[str, dict]:
        return {
            "entities": json_file("entities.json")
        }
