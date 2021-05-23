from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import widgets
from django.http.response import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse

from cm.db import fields

# FIXME: These overrrides would be better done by specifying a form field in the field class, instead of
# overwriting them in the admin.


class BaseAdmin(admin.ModelAdmin):
    formfield_overrides = {
        fields.SmallTextField: {"widget": widgets.TextInput},
    }

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_duplicate"] = getattr(self, "show_duplicate", False)
        print("form_url= " + str(form_url))
        print("self=" + str(self))
        print("extra_context" + str(extra_context))

        try:
            return super().changeform_view(
                request,
                object_id=object_id,
                form_url=form_url,
        #        extra_context=extra_context,
            )
        except ValidationError as e:
            if request.user.is_superuser:
                message = str(e)
            else:
                message = "Something went wrong!"
            return HttpResponseBadRequest(message)

    def response_change(self, request, obj):
        if "_duplicate" in request.POST and hasattr(self, "_duplicated_id"):
            url_name = f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change"
            return HttpResponseRedirect(reverse(url_name, args=(self._duplicated_id,)))

        return super().response_change(request, obj)

    def save_model(self, request, obj, form, change):
        print("sono in save model")
        if not obj.pk:
            # Only set created_by during the first save.
            obj.created_by = request.user

        if "_duplicate" in request.POST:
            original_name = str(obj)
            obj = obj.duplicate()
            self._duplicated_id = obj.id
            self.message_user(request, f"{original_name} was duplicated!")
            return

        super().save_model(request, obj, form, change)

    def formfield_callback(self, db_field, formfield, request, obj=None):
        return formfield

    def get_form(self, request, obj=None, **kwargs):
        def formfield_callback(db_field):
            formfield = self.formfield_for_dbfield(db_field, request=request)
            formfield = self.formfield_callback(db_field, formfield, request, obj)
            return formfield

        return super().get_form(
            request, obj=obj, formfield_callback=formfield_callback, **kwargs
        )


class BaseTabularInline(admin.TabularInline):
    formfield_overrides = {
        fields.SmallTextField: {"widget": widgets.TextInput},
    }

    def formfield_callback(self, db_field, formfield, request, parent=None):
        return formfield

    def get_formset(self, request, parent=None, **kwargs):
        def formfield_callback(db_field):
            formfield = self.formfield_for_dbfield(db_field, request=request)
            formfield = self.formfield_callback(db_field, formfield, request, parent)
            return formfield

        return super().get_formset(
            request, obj=parent, formfield_callback=formfield_callback, **kwargs
        )
