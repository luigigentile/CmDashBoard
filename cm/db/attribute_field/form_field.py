import json

from django.forms import ValidationError
from django.forms.boundfield import BoundField
from django.forms.fields import InvalidJSONInput, JSONField

from .sentry_types import EncodedDict, JSONString
from .transform import (
    db_encoded_to_python,
    form_encoded_to_python,
    python_to_form_encoded,
)
from .widget import AttributeWidget


class BoundAttributeField(BoundField):
    def as_widget(self, widget=None, attrs=None, only_initial=False):
        """Overwritten version of BoundAttributeField that passes the instance to the widget.

        Note this only works with a widget that accepts instance as an attribute,
        it's meant to be used specifically with AttributeWidget.
        """
        widget = self.field.widget
        if self.field.localize:
            widget.is_localized = True
        attrs = attrs or {}
        attrs = self.build_widget_attrs(attrs, widget)
        if self.auto_id and "id" not in widget.attrs:
            attrs.setdefault(
                "id", self.html_initial_id if only_initial else self.auto_id
            )

        return widget.render(
            name=self.html_initial_name if only_initial else self.html_name,
            value=self.value(),
            attrs=attrs,
            renderer=self.form.renderer,
            instance=self.form.instance,
        )

    def value(self):
        """Overwritten version of value that passes the instance to the widget.

        Note that this only works for a widget that accepts an instance as an attribute to `bound_data`,
        it's meant to be use specifically with AttributeWidget.

        The only reason this function is needed is that we need the instance to process the submitted form
        in case there is a form error (which calls bound_data before render)
        """
        data = self.initial
        if self.form.is_bound:
            data = self.field.bound_data(self.data, data, instance=self.form.instance)
        return self.field.prepare_value(data)


class AttributeField(JSONField):
    widget = AttributeWidget

    def prepare_value(self, value):
        if isinstance(value, InvalidJSONInput):
            return super().prepare_value(value)
        return value

    def to_python(self, value):
        if self.disabled:
            return value
        if value in self.empty_values:
            return None
        elif isinstance(value, (list, dict, int, float, JSONString)):
            return value

        try:
            converted = db_encoded_to_python(json.loads(value))
        except json.JSONDecodeError:
            raise ValidationError(
                self.error_messages["invalid"], code="invalid", params={"value": value},
            )

        if isinstance(converted, str):
            return JSONString(converted)
        else:
            return converted

    def bound_data(self, data, initial, instance=None):
        if self.disabled:
            return initial

        # Bound data can be called with previously submitted data in case of validation errors.
        # This is the invalid data that the user submitted, which we need to decode (and reencode in render).
        # This is a little bit tricky because by definition we won't be able to instantiate some of the invalid data
        # in python.
        # Because of that, we
        #   1) decode the parts of the submited data that are valid
        #   2) reencoded that data to form data
        #   3) add the raw submitted values back to the reencoded data
        if isinstance(data, dict):
            attribute_definitions = (
                instance.attribute_definitions() if instance.pk else None
            )
            if attribute_definitions is None:
                return initial

            # Decode the (presumed invalid) submitted data without raising errors for invalid data.
            # This will simply ignore invalid values
            decoded_data = form_encoded_to_python(
                data, attribute_definitions, None, raise_errors=False
            )
            # Encode the data back to form data
            encoded_data = python_to_form_encoded(decoded_data, attribute_definitions)

            # Now add the initially submitted data back exactly as submitted
            for k, v in data.items():
                encoded_data[k]["value"] = v

            # Use a sentry type to signal to Widget.render that this data is already processed and shouldn't be
            # processed again.
            return EncodedDict(encoded_data)

        # Read the raw json and parse it into a python object with the correct units
        try:
            return db_encoded_to_python(json.loads(data))
        except json.JSONDecodeError:
            return InvalidJSONInput(data)

    def get_bound_field(self, form, field_name):
        """Return a BoundField subclass that will allows us to use instance data in the widget."""
        return BoundAttributeField(form, self, field_name)

    def clean(self, value):
        return value
