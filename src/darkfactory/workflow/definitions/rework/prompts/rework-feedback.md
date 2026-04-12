<!-- NOTE: This file is a FORMAT REFERENCE only. It is NOT rendered by the
     template system (which only supports {{NAME}} placeholders, not Jinja).
     The actual rendering is performed by render_rework_feedback() in
     src/darkfactory/rework_prompt.py. Keep this in sync if the format changes. -->
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
