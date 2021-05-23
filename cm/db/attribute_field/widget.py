from typing import Optional

from django.forms.widgets import Widget

from cm.data.units import Quantity
from cm.db.attribute_field.sentry_types import EncodedDict
from cm.db.attribute_field.transform import python_to_form_encoded


class AttributeWidget(Widget):
    template_name = "admin/db/attribute_widget.html"

    def __init__(self, attrs=None):
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        return context

    def _format_single_value(self, value):
        if isinstance(value, list):
            return ", ".join(value)
        if isinstance(value, Quantity):
            return str(value)
        return value

    def format_value(self, value):
        if not isinstance(value, dict):
            return value

        return {k: self._format_single_value(v) for k, v in value.items()}

    def value_from_datadict(self, data, files, name):
        processed = {}
        for key, value in data.items():
            if key.startswith(f"{name}__"):
                attribute_name = key.split(f"{name}__", 1)[-1]
                processed[attribute_name] = value

        return processed

    def value_omitted_from_data(self, data, files, name):
        for key in data:
            if key.startswith(f"{name}__"):
                return False
        return True

    def render(self, name, value, attrs=None, renderer=None, instance=None):
        """Render the widget as an HTML string."""
        processed_value: Optional[EncodedDict]

        if isinstance(value, EncodedDict):
            # Don't re-process the data if it was already processed (this happens for example on validation errors)
            processed_value = value
        else:
            # We can only fetch the attribute definitions if the instance has been saved
            if not instance.pk:
                attribute_definitions = None
            else:
                attribute_definitions = instance.attribute_definitions()

            if attribute_definitions is not None:
                processed_value = python_to_form_encoded(value, attribute_definitions)
            else:
                processed_value = None

        context = self.get_context(name, processed_value, attrs)
        context["instance"] = instance

        return self._render(self.template_name, context, renderer)
