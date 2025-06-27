import json
import sys
import anthropic
import inquirer
from colors import Colors
from state_machine import State, Transition
from with_step import with_step, with_streaming_step
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


def to_entities(raw_data):
    return [Entity(**item) for item in raw_data]

def extract_models_and_fields(prompt: str) -> List[Entity]:
    """
    Uses Claude to extract a list of Django models and their fields from the prompt.
    Returns a list of Entity objects with fields and relationships.
    """
    client = anthropic.Anthropic()
    system_prompt = (
        "You are an expert Django developer. Given a user prompt, extract a list of Django models and their fields. "
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

    with with_streaming_step("Extracting models and fields from Claude...") as token_count:
        response_text = ""
        with client.messages.stream(
            model="claude-3-7-sonnet-latest",
            max_tokens=2048,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                token_count[0] += len(text.split())

    return json.loads(response_text.strip())

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

    with with_streaming_step("Refining entities based on feedback...") as token_count:
        response_text = ""
        with client.messages.stream(
            model="claude-3-5-sonnet-latest",
            max_tokens=1024,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                token_count[0] += len(text.split())

    return json.loads(response_text.strip())

def display_entities(entities: List[Entity]):
    """Display entities in a formatted way"""
    print("Entities extracted:")
    for entity in entities:
        print(f"  - {Colors.BOLD}{Colors.BRIGHT_GREEN}{entity.name}{Colors.END}")
        for rel_field, rel_info in entity.relationships.items():
            print(f"      {Colors.BRIGHT_MAGENTA}{rel_field}{Colors.END}: {rel_info['type']} -> {Colors.BRIGHT_GREEN}{rel_info['related_to']}{Colors.END}")
        for field, ftype in entity.fields.items():
            print(f"      {Colors.BRIGHT_YELLOW}{field}{Colors.END}: {ftype}")

def get_entities_confirmation(entities: dict, original_prompt: str = "") -> Tuple[bool, dict]:
    """
    Ask user to confirm entities or provide feedback for changes.
    Returns (should_proceed, final_entities)
    """
    current_entities = entities

    while True:
        display_entities(to_entities(current_entities))
        print(f"\n{Colors.BOLD}Please review the extracted entities:{Colors.END}")

        questions = [
            inquirer.List(
                'action',
                message="What would you like to do?",
                choices=[
                    ('Yes, proceed with these entities', 'proceed'),
                    ('Modify the entities', 'modify')
                ],
                carousel=True
            )
        ]

        try:
            answers = inquirer.prompt(questions)
            if not answers:  # User pressed Ctrl+C
                print(f"\n{Colors.BRIGHT_YELLOW}Cancelled by user{Colors.END}")
                sys.exit(0)

            action = answers['action']

            if action == 'proceed':
                return True, current_entities
            elif action == 'modify':
                feedback_question = [
                    inquirer.Text(
                        'feedback',
                        message="What would you like to change?",
                        validate=lambda _, x: len(x.strip()) > 0 or "Please provide feedback"
                    )
                ]

                feedback_answers = inquirer.prompt(feedback_question)
                if not feedback_answers:
                    continue

                feedback = feedback_answers['feedback']
                print(f"\n{Colors.BRIGHT_CYAN}Refining entities...{Colors.END}")
                current_entities = refine_entities(original_prompt, current_entities, feedback)
                print(f"{Colors.BRIGHT_GREEN}Entities updated{Colors.END}\n")

        except KeyboardInterrupt:
            print(f"\n{Colors.BRIGHT_YELLOW}Cancelled by user{Colors.END}")
            sys.exit(0)

class ExtractEntities(Transition):
    def run(self, state: State) -> State:
        spec = state["spec"]

        entities = extract_models_and_fields(spec)

        return state.clone({
            "entities": entities
        })

class RefineEntities(Transition):
    def run(self, state: State) -> State:
        spec = state["spec"]
        entities = state["entities"]

        # Get user confirmation for entities
        should_proceed, final_entities = get_entities_confirmation(entities, spec)
        if not should_proceed:
            print(f"{Colors.BRIGHT_YELLOW}Project generation cancelled{Colors.END}")
            sys.exit(0)

        return state.clone({
            "entities": final_entities
        })