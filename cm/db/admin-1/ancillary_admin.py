from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from cm.db.attribute_field.transform import decode_form_value
from cm.db.constants import AncillaryAppliesTo, AncillaryOperator, AncillaryType
from cm.db.models import (
    Ancillary,
    AncillaryAttribute,
    AncillaryConnection,
    AttributeDefinition,
    Category,
    InterfacePin,
    Pin,
    PinAssignment,
)

from .base_admin import BaseAdmin, BaseTabularInline


class AttributeInline(BaseTabularInline):
    model = AncillaryAttribute
    exclude = ["created_by", "interface_type"]
    extra = 1

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "attribute_definition" and parent is not None:
            try:
                category = parent.get_category()
            except Category.DoesNotExist:
                formfield.queryset = AttributeDefinition.objects.none()
            else:
                formfield.queryset = AttributeDefinition.objects.filter(
                    category__in=category.get_ancestors(include_self=True)
                )
        return formfield


class ConnectionForm(forms.ModelForm):
    class Meta:
        model = AncillaryConnection
        fields = [
            "pin",
            "interface_pin",
            "ancillary_pin",
            "role",
            "pin_assignment",
        ]

    logical_network = forms.ChoiceField(required=False)

    def __init__(self, *args, parent, **kwargs):
        from cm.data import interface_family as data_interface_family
        from cm.data import interface_pin as data_interface_pin

        super().__init__(*args, **kwargs)

        self.logical_networks = {}
        if parent.interface_family_id:
            interface_families = data_interface_family.InterfaceFamily.get_all()
            data_parent = [
                family
                for family in interface_families
                if family.id == parent.interface_family_id
            ][0]

            self.logical_networks = data_parent.get_logical_networks()
            self.fields["logical_network"].required = True
            self.fields["logical_network"].choices = [(None, "-")] + [
                (network_name, network_name) for network_name in self.logical_networks  # type: ignore
            ]
            self.fields["interface_pin"].required = False
            self.fields["interface_pin"].widget = forms.HiddenInput()
            self.fields["pin_assignment"].widget = forms.HiddenInput()

            self.fields["pin"].required = False
            self.fields["pin"].widget = forms.HiddenInput()

            if self.instance and self.instance.interface_pin_id:
                try:
                    self.fields[
                        "logical_network"
                    ].initial = data_parent.get_logical_network(
                        data_interface_pin.InterfacePin._from_db(
                            self.instance.interface_pin
                        )
                    ).name
                except KeyError:
                    # The family was changed and this logical net no longer exists
                    self.fields["logical_network"].initial = None
        elif parent.applies_to == AncillaryAppliesTo.pins:
            self.fields["pin"].required = True
            self.fields["interface_pin"].widget = forms.HiddenInput()
            # self.fields["interface_pin"].value = None
            self.fields["pin_assignment"].widget = forms.HiddenInput()
            self.fields["logical_network"].widget = forms.HiddenInput()
        else:
            self.fields["logical_network"].widget = forms.HiddenInput()
            self.fields["pin"].required = False
            self.fields["pin"].widget = forms.HiddenInput()

    def clean_logical_network(self):
        if self.logical_networks and self.cleaned_data:
            network_name = self.cleaned_data.get("logical_network")
            if not network_name or network_name not in self.logical_networks:
                raise ValidationError(
                    {
                        "logical_network": f"Logical network {network_name} does not exist in this ancillary's family!"
                    }
                )
            else:
                network = self.logical_networks[network_name]

                # Pick a requesting pin, any one will do (every requesting pin can only ever be in one logical network)
                self.cleaned_data["interface_pin"] = InterfacePin.objects.get(
                    id=next(iter(network.requesting_pins)).id
                )


class ConnectionFormSet(forms.BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["parent"] = self.instance
        return kwargs


class PinChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj} - ({obj.connectivity.name})"


class ConnectionInline(BaseTabularInline):
    model = AncillaryConnection
    form = ConnectionForm
    formset = ConnectionFormSet
    extra = 1

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if parent is not None:
            if db_field.name == "interface_pin" and parent.interface_family_id is None:
                formfield.queryset = InterfacePin.objects.filter(
                    interface_type_id__in=parent.get_interface_type_ids()
                )
            elif db_field.name == "pin":
                if parent.subcircuit_id:
                    formfield.queryset = (
                        formfield.queryset.filter(
                            connectivity__block_filters__subcircuit_id=parent.subcircuit_id
                        )
                        .order_by("name")
                        .distinct()
                    )
            elif db_field.name == "pin_assignment":
                if parent.interface_id:
                    formfield.queryset = parent.interface.pin_assignments.all()
                else:
                    formfield.queryset = PinAssignment.objects.none()
            elif db_field.name == "ancillary_pin":
                if parent.connectivity_id:
                    formfield.queryset = parent.connectivity.pins.all()
                else:
                    formfield.queryset = Pin.objects.none()
        return formfield

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "pin":
            return PinChoiceField(
                queryset=Pin.objects.all().order_by("connectivity__name"),
                required=False,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        print(self.errors)


class AncillaryForm(forms.ModelForm):
    class Meta:
        model = Ancillary
        fields = (
            "ancillary_type",
            "applies_to",
            "connectivity",
            "maximum_latency",
         )


@admin.register(Ancillary)
class AncillaryAdmin(BaseAdmin):
    form = AncillaryForm
    readonly_fields = ("target", "subcircuit")
    inlines = [ConnectionInline, AttributeInline]

    def target(self, instance):
        if instance.interface_id:
            return str(instance.interface)
        elif instance.interface_type_id:
            return str(instance.interface_type)
        elif instance.interface_family_id:
            return str(instance.interface_family)
        return "-"

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        print(self.errors)


class AncillaryInlineBaseForm(forms.ModelForm):
    class Meta:
        model = Ancillary
        fields = (
            "applies_to",
            "ancillary_type",
            "interface",
            "connectivity",
            "capacitance_resistance_impedance",
            "dcresistance_tolerance",
            "maximum_latency",
        )

    capacitance_resistance_impedance = forms.CharField(
        required=False,
        help_text="Capacitance for capacitors, Resistance for resistors, Impedance@Hz for ferrite beads",
    )
    dcresistance_tolerance = forms.CharField(
        required=False,
        help_text="Tolerance for capacitors and resistors, dc_resistancer for ferrite beads",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # For existing non-custom instances, pull in the initial values for the two main values
        # (these are fields that we show on the inline to make it easier to edit ancillaries without lots of clicks)
        if (
            self.instance._target_objects()
            and self.instance.ancillary_type != AncillaryType.custom
        ):
            self.fields["capacitance_resistance_impedance"].required = True

            attribute_definitions = self.instance.get_main_attributes()
            main_attribute = AncillaryAttribute.objects.filter(
                ancillary=self.instance, attribute_definition=attribute_definitions[0],
            ).first()
            if main_attribute:
                self.fields[
                    "capacitance_resistance_impedance"
                ].initial = main_attribute.value

            secondary_attribute = AncillaryAttribute.objects.filter(
                ancillary=self.instance, attribute_definition=attribute_definitions[1],
            ).first()
            if secondary_attribute:
                self.fields[
                    "dcresistance_tolerance"
                ].initial = secondary_attribute.value

        else:
            if self.instance.ancillary_type == AncillaryType.custom:
                self._disable_fields(
                    ("capacitance_resistance_impedance", "dcresistance_tolerance",)
                )

        # Don't allow changing the ancillary type after the ancillary was created (would invalidate the connections)
        if self.instance and not self.instance._state.adding:
            self._disable_fields(["ancillary_type"])

    def clean(self):
        cleaned_data = super().clean()

        instance = self.instance
        # we need to manually update the type of the ancillary and its connectivity,
        # because instance attributes won'thave been updated yet
        instance.ancillary_type = cleaned_data.get("ancillary_type")
        instance.connectivity = cleaned_data.get("connectivity")
        if (
            not instance.ancillary_type
            or instance.ancillary_type == AncillaryType.custom
        ):
            return

        attribute_definitions = instance.get_main_attributes()

        main_value = cleaned_data.get("capacitance_resistance_impedance", "")
        if main_value:
            try:
                decode_form_value(
                    name="capacitance_resistance_impedance",
                    value=main_value,
                    attribute_definition=attribute_definitions[0],
                )
            except ValueError as e:
                raise ValidationError({"capacitance_resistance_impedance": str(e)})

        secondary_value = cleaned_data.get("dcresistance_tolerance", "")
        if secondary_value:
            try:
                decode_form_value(
                    name="dcresistance_tolerance",
                    value=secondary_value,
                    attribute_definition=attribute_definitions[1],
                )
            except ValueError as e:
                raise ValidationError({"dcresistance_tolerance": str(e)})

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=commit)

        if not commit:
            return instance

        if instance.ancillary_type == AncillaryType.custom:
            return instance

        attribute_definitions = instance.get_main_attributes()

        main_value = self.cleaned_data.get("capacitance_resistance_impedance")
        if main_value:
            main_attribute, _ = AncillaryAttribute.objects.get_or_create(
                ancillary=instance,
                attribute_definition=attribute_definitions[0],
                defaults={"value": main_value, "operator": AncillaryOperator.exact},
            )
            main_attribute.value = main_value
            main_attribute.save()

        secondary_value = self.cleaned_data.get("dcresistance_tolerance", "")
        if secondary_value:
            secondary_attribute, _ = AncillaryAttribute.objects.get_or_create(
                ancillary=instance,
                attribute_definition=attribute_definitions[1],
                defaults={
                    "value": secondary_value,
                    "operator": AncillaryOperator.exact,
                },
            )
            secondary_attribute.value = secondary_value
            secondary_attribute.save()

        return instance

    def _disable_fields(self, field_names):
        """Disable a list of form field."""
        for field_name in field_names:
            if field_name in self.fields:
                self.fields[field_name].disabled = True
                self.fields[field_name].widget.can_add_related = False
                self.fields[field_name].widget.can_change_related = False
                self.fields[field_name].widget.can_view_related = False
