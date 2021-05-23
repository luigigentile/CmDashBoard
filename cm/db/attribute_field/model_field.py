from django.db import models
from psycopg2.extras import Json

# NOTE: this module must not import anything that requires django to already be set up, because the class itself
# needs to be included in the django settings.


class AttributeField(models.JSONField):
    def formfield(self, **kwargs):
        from . import form_field

        return form_field.AttributeField()

    def from_db_value(self, value, expression, connection):
        # Non-dict values can happen when doing special lookups, like fetching only dict keys
        # In that case we just want to return the raw value.
        value = super().from_db_value(value, expression, connection)
        from . import transform

        if not isinstance(value, dict):
            return value
        return transform.db_encoded_to_python(value)

    def get_db_prep_value(self, value, connection, prepared=False):
        """Convert a python value to a db backend value.

        This is different from get_prep_value because we need to look up attributes by just their
        name and value, but when storing quantities we also need to store the original unit, so that we can
        translate the database value back into a quantity. """
        from . import transform

        if value is None:
            return super().get_db_prep_value(value, connection, prepared=prepared)

        if isinstance(value, Json):
            return value

        if not isinstance(value, dict):
            # Non-dict values can happen when doing more advanced lookups, like __has_key=<key>
            return super().get_db_prep_value(value, connection, prepared=prepared)

        return super().get_prep_value(transform.python_to_db_encoded(value))

    def validate(self, value, model_instance):
        # We need to overwrite this to avoid the parent class overzealously validating data as json.
        pass

    def save_form_data(self, instance, data):
        from . import transform

        attribute_definitions = instance.attribute_definitions()
        processed = transform.form_encoded_to_python(
            data, attribute_definitions, self.get_attname()
        )
        setattr(instance, self.get_attname(), processed)

    @classmethod
    def lookup_missing(cls, attribute_name, field_name="attributes"):
        return models.Q(**{f"{field_name}__{attribute_name}__isnull": True}) | models.Q(
            **{f"{field_name}__{attribute_name}__in": [None, ""]}
        )
