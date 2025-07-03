from fastapi import FastAPI
from typing import List, Optional, Dict, Any
{% if entities %}
from .models import {{ entities|map(attribute='name')|join(', ') }}
{% else %}
# No entities defined
{% endif %}

app = FastAPI()
