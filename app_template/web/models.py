from django.db import models

{% for entity in entities %}
class {{ entity.name }}(models.Model):
{% for field_name, field_type in entity.fields.items() %}
    {{ field_name }} = models.{{ field_type }}
{% endfor %}
{% for rel_field, rel_info in entity.relationships.items() %}{% if rel_info.type == 'ForeignKey' %}
    {{ rel_field }} = models.ForeignKey('{{ rel_info.related_to }}', on_delete=models.CASCADE)
{% elif rel_info.type == 'ManyToManyField' %}
    {{ rel_field }} = models.ManyToManyField('{{ rel_info.related_to }}')
{% elif rel_info.type == 'OneToOneField' %}
    {{ rel_field }} = models.OneToOneField('{{ rel_info.related_to }}', on_delete=models.CASCADE)
{% endif %}{% endfor %}
{% if not loop.last %}

{% endif %}
{% endfor %}
