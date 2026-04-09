{% for thread in threads %}
### Comment by {{ thread.author }}{% if thread.path %} on `{{ thread.path }}`{% if thread.line %}:{{ thread.line }}{% endif %}{% endif %}

> {{ thread.body }}
{% if thread.replies %}

**Thread replies:**
{% for reply in thread.replies %}
> **{{ reply.author }}:** {{ reply.body }}
{% endfor %}
{% endif %}

---
{% endfor %}
