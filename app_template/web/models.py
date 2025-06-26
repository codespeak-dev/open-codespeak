from django.db import models

{% for entity in entities %}
class {{ entity.name }}(models.Model):
{% for field_name, field_type in entity.fields.items() %}
    {{ field_name }} = models.{{ field_type }}
{% endfor %}
{% if not loop.last %}

{% endif %}
{% endfor %}
