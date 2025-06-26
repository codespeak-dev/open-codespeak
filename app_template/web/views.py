from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from asgiref.sync import sync_to_async
from .models import {{ entities|map(attribute='name')|join(', ') }}

app = FastAPI()

{% set entity_names = entities|map(attribute='name')|list %}
{% for entity in entities %}
{# Create basic Pydantic models #}
class {{ entity.name }}Base(BaseModel):
{% for field_name, field_type in entity.fields.items() %}
{% if 'CharField' in field_type %}
    {{ field_name }}: str
{% elif 'IntegerField' in field_type %}
    {{ field_name }}: int
{% elif 'BooleanField' in field_type %}
    {{ field_name }}: bool
{% elif 'DateTimeField' in field_type %}
    {{ field_name }}: str
{% elif 'TextField' in field_type %}
    {{ field_name }}: str
{% else %}
    {{ field_name }}: str
{% endif %}
{% endfor %}

class {{ entity.name }}Create({{ entity.name }}Base):
{% for rel_field, rel_info in entity.relationships.items() %}
{% if rel_info.type == 'ForeignKey' %}
    {{ rel_field }}_id: int
{% endif %}
{% endfor %}
    pass

class {{ entity.name }}Response({{ entity.name }}Base):
    id: int
{% for rel_field, rel_info in entity.relationships.items() %}
{% if rel_info.type == 'ForeignKey' %}
    {{ rel_field }}: Optional['{{ rel_info.related_to }}Response'] = None
{% elif rel_info.type == 'ManyToManyField' %}
    {{ rel_field }}: List['{{ rel_info.related_to }}Response'] = []
{% endif %}
{% endfor %}

    class Config:
        from_attributes = True

{% endfor %}

{# Generate CRUD endpoints for each entity #}
{% for entity in entities %}
@app.post("/{{ entity.name.lower() }}/", response_model={{ entity.name }}Response)
async def create_{{ entity.name.lower() }}({{ entity.name.lower() }}: {{ entity.name }}Create):
    db_{{ entity.name.lower() }} = {{ entity.name }}(**{{ entity.name.lower() }}.dict())
    await sync_to_async(db_{{ entity.name.lower() }}.save)()
    return {{ entity.name }}Response.from_attributes(db_{{ entity.name.lower() }})

@app.get("/{{ entity.name.lower() }}/", response_model=List[{{ entity.name }}Response])
async def read_{{ entity.name.lower() }}s():
    {{ entity.name.lower() }}s = await sync_to_async(list)({{ entity.name }}.objects.all())
    return [{{ entity.name }}Response.from_attributes({{ entity.name.lower() }}) for {{ entity.name.lower() }} in {{ entity.name.lower() }}s]

@app.get("/{{ entity.name.lower() }}/{item_id}", response_model={{ entity.name }}Response)
async def read_{{ entity.name.lower() }}(item_id: int):
    try:
        {{ entity.name.lower() }} = await sync_to_async({{ entity.name }}.objects.get)(id=item_id)
        return {{ entity.name }}Response.from_attributes({{ entity.name.lower() }})
    except {{ entity.name }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ entity.name }} not found")

@app.put("/{{ entity.name.lower() }}/{item_id}", response_model={{ entity.name }}Response)
async def update_{{ entity.name.lower() }}(item_id: int, {{ entity.name.lower() }}: {{ entity.name }}Create):
    try:
        db_{{ entity.name.lower() }} = await sync_to_async({{ entity.name }}.objects.get)(id=item_id)
        for field, value in {{ entity.name.lower() }}.dict().items():
            setattr(db_{{ entity.name.lower() }}, field, value)
        await sync_to_async(db_{{ entity.name.lower() }}.save)()
        return {{ entity.name }}Response.from_attributes(db_{{ entity.name.lower() }})
    except {{ entity.name }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ entity.name }} not found")

@app.delete("/{{ entity.name.lower() }}/{item_id}")
async def delete_{{ entity.name.lower() }}(item_id: int):
    try:
        {{ entity.name.lower() }} = await sync_to_async({{ entity.name }}.objects.get)(id=item_id)
        await sync_to_async({{ entity.name.lower() }}.delete)()
        return {"message": "{{ entity.name }} deleted successfully"}
    except {{ entity.name }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ entity.name }} not found")

{# Generate nested endpoints for relationships #}
{% for rel_field, rel_info in entity.relationships.items() %}
{% if rel_info.type == 'ForeignKey' %}
{# Many-to-one relationship: get all items that belong to a parent #}
@app.get("/{{ rel_info.related_to.lower() }}/{parent_id}/{{ entity.name.lower() }}/", response_model=List[{{ entity.name }}Response])
async def read_{{ entity.name.lower() }}s_by_{{ rel_info.related_to.lower() }}(parent_id: int):
    try:
        parent = await sync_to_async({{ rel_info.related_to }}.objects.get)(id=parent_id)
        {{ entity.name.lower() }}s = await sync_to_async(list)({{ entity.name }}.objects.filter({{ rel_field }}_id=parent_id))
        return [{{ entity.name }}Response.from_attributes({{ entity.name.lower() }}) for {{ entity.name.lower() }} in {{ entity.name.lower() }}s]
    except {{ rel_info.related_to }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ rel_info.related_to }} not found")

@app.post("/{{ rel_info.related_to.lower() }}/{parent_id}/{{ entity.name.lower() }}/", response_model={{ entity.name }}Response)
async def create_{{ entity.name.lower() }}_for_{{ rel_info.related_to.lower() }}(parent_id: int, {{ entity.name.lower() }}: {{ entity.name }}Base):
    try:
        {{ rel_field }} = await sync_to_async({{ rel_info.related_to }}.objects.get)(id=parent_id)
{% for other_rel_field, other_rel_info in entity.relationships.items() %}{% if other_rel_info.type == 'ForeignKey' and other_rel_field != rel_field %}
        {{ other_rel_field }} = await sync_to_async({{ other_rel_info.related_to }}.objects.get)(id={{ other_rel_field }}_id)
{% endif %}{% endfor %}
        data = {{ entity.name.lower() }}.dict()
        db_{{ entity.name.lower() }} = {{ entity.name }}({{ rel_field }}={{ rel_field }}{% for other_rel_field, other_rel_info in entity.relationships.items() %}{% if other_rel_info.type == 'ForeignKey' and other_rel_field != rel_field %}, {{ other_rel_field }}={{ other_rel_field }}{% endif %}{% endfor %}, **data)
        await sync_to_async(db_{{ entity.name.lower() }}.save)()
        return {{ entity.name }}Response.model_validate(db_{{ entity.name.lower() }})
    except {{ rel_info.related_to }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ rel_info.related_to }} not found")
{% for other_rel_field, other_rel_info in entity.relationships.items() %}{% if other_rel_info.type == 'ForeignKey' and other_rel_field != rel_field %}
    except {{ other_rel_info.related_to }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ other_rel_info.related_to }} not found")
{% endif %}{% endfor %}

{% elif rel_info.type == 'ManyToManyField' %}
{# Many-to-many relationship endpoints #}
@app.get("/{{ entity.name.lower() }}/{item_id}/{{ rel_field }}/", response_model=List[{{ rel_info.related_to }}Response])
async def read_{{ entity.name.lower() }}_{{ rel_field }}(item_id: int):
    try:
        {{ entity.name.lower() }} = await sync_to_async({{ entity.name }}.objects.get)(id=item_id)
        related_items = await sync_to_async(list)({{ entity.name.lower() }}.{{ rel_field }}.all())
        return [{{ rel_info.related_to }}Response.from_attributes(item) for item in related_items]
    except {{ entity.name }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ entity.name }} not found")

@app.post("/{{ entity.name.lower() }}/{item_id}/{{ rel_field }}/{related_id}")
async def add_{{ entity.name.lower() }}_{{ rel_field }}(item_id: int, related_id: int):
    try:
        {{ entity.name.lower() }} = await sync_to_async({{ entity.name }}.objects.get)(id=item_id)
        related_item = await sync_to_async({{ rel_info.related_to }}.objects.get)(id=related_id)
        await sync_to_async({{ entity.name.lower() }}.{{ rel_field }}.add)(related_item)
        return {"message": "{{ rel_info.related_to }} added to {{ entity.name }}"}
    except {{ entity.name }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ entity.name }} not found")
    except {{ rel_info.related_to }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ rel_info.related_to }} not found")

@app.delete("/{{ entity.name.lower() }}/{item_id}/{{ rel_field }}/{related_id}")
async def remove_{{ entity.name.lower() }}_{{ rel_field }}(item_id: int, related_id: int):
    try:
        {{ entity.name.lower() }} = await sync_to_async({{ entity.name }}.objects.get)(id=item_id)
        related_item = await sync_to_async({{ rel_info.related_to }}.objects.get)(id=related_id)
        await sync_to_async({{ entity.name.lower() }}.{{ rel_field }}.remove)(related_item)
        return {"message": "{{ rel_info.related_to }} removed from {{ entity.name }}"}
    except {{ entity.name }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ entity.name }} not found")
    except {{ rel_info.related_to }}.DoesNotExist:
        raise HTTPException(status_code=404, detail="{{ rel_info.related_to }} not found")

{% endif %}
{% endfor %}

{% if not loop.last %}

{% endif %}
{% endfor %}