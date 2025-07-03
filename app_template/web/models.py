from django.db import models

{% for entity in entities %}
class {{ entity.name }}(models.Model):
{% for field in entity.fields %}
    {{ field.name }} = models.{{ field.type }}
{% endfor %}
{% for rel in entity.relationships %}{% if rel.type == 'ForeignKey' %}
    {{ rel.name }} = models.ForeignKey('{{ rel.related_to }}', on_delete=models.CASCADE, related_name='{{ rel.related_name }}')
{% elif rel.type == 'ManyToManyField' %}
    {{ rel.name }} = models.ManyToManyField('{{ rel.related_to }}')
{% elif rel.type == 'OneToOneField' %}
    {{ rel.name }} = models.OneToOneField('{{ rel.related_to }}', on_delete=models.CASCADE)
{% endif %}{% endfor %}
{% if not loop.last %}

{% endif %}
{% endfor %}
