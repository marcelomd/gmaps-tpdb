from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from .models import Class, Subclass, Treatment, Reference, Compound, FormulaMass, ExcelUpload, UserEvent


class CompoundAdmin(admin.ModelAdmin):
    class Media:
        js = ('admin/js/compound_admin.js',)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Only original compounds can be a parent; TPs don't chain
        if db_field.name == "origin":
            kwargs["queryset"] = Compound.objects.filter(origin=None)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        self.remove_orphan_formulas()

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        self.remove_orphan_formulas()

    def remove_orphan_formulas(self):
        # FormulaMass rows are shared between compounds, so they only go once nothing uses them
        FormulaMass.objects.filter(compound__isnull=True).delete()

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('ajax/load-subclasses/', self.admin_site.admin_view(self.load_subclasses), name='core_compound_ajax_load_subclasses'),
        ]
        return custom_urls + urls
    
    def load_subclasses(self, request):
        class_id = request.GET.get('class_id')
        subclasses = Subclass.objects.filter(clas_id=class_id).order_by('name')
        return JsonResponse(list(subclasses.values('id', 'name')), safe=False)


class ExcelUploadAdmin(admin.ModelAdmin):
    list_display = ['file', 'uploader', 'uploaded_at', 'status', 'records_imported', 'clear_existing_data']
    list_filter = ['status', 'uploaded_at', 'clear_existing_data']
    readonly_fields = ['uploaded_by', 'former_user_email', 'former_user_name', 'uploaded_at', 'status', 'records_imported', 'error_message']
    fields = ['file', 'clear_existing_data', 'uploaded_by', 'former_user_email', 'former_user_name', 'uploaded_at', 'status', 'records_imported', 'error_message']

    def uploader(self, obj):
        return obj.user_label(obj.uploaded_by)
    uploader.short_description = 'Uploaded by'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


class UserEventAdmin(admin.ModelAdmin):
    list_display = ['user_email', 'event_type', 'timestamp', 'event_details']
    list_filter = ['event_type', 'timestamp']
    search_fields = ['user__email', 'former_user_email', 'former_user_name']
    readonly_fields = ['user', 'former_user_email', 'former_user_name', 'event_type', 'timestamp', 'extra_data']
    date_hierarchy = 'timestamp'

    def user_email(self, obj):
        return obj.user_label(obj.user)
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'

    def event_details(self, obj):
        if not obj.extra_data:
            return '-'

        if obj.event_type == 'view':
            page = obj.extra_data.get('page', '-')
            url = obj.extra_data.get('url', '-')
            return f"{page} ({url})"
        elif obj.event_type in ('login', 'register'):
            return f"IP: {obj.extra_data.get('ip', '-')}"
        elif obj.event_type == 'query':
            filters = obj.extra_data.get('filters', {})
            if filters:
                filter_str = ', '.join([f"{k}={v}" for k, v in filters.items()])
                return filter_str[:100]
            return 'No filters'
        elif obj.event_type == 'import':
            filename = obj.extra_data.get('filename', '-')
            records = obj.extra_data.get('records_imported', 0)
            cleared = obj.extra_data.get('clear_existing_data', False)
            clear_str = " (cleared data)" if cleared else ""
            return f"{filename}: {records} records{clear_str}"

        return '-'
    event_details.short_description = 'Details'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Class)
admin.site.register(Subclass)
admin.site.register(Treatment)
admin.site.register(Reference)
admin.site.register(Compound, CompoundAdmin)
admin.site.register(ExcelUpload, ExcelUploadAdmin)
admin.site.register(UserEvent, UserEventAdmin)