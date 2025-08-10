from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.core.management import call_command
from django.db import transaction
import os
from .models import Class, Subclass, Treatment, Reference, Compound, ExcelUpload


class CompoundAdmin(admin.ModelAdmin):
    class Media:
        js = ('admin/js/compound_admin.js',)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "origin":
            kwargs["queryset"] = Compound.objects.filter(origin=None)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
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
    list_display = ['file', 'uploaded_by', 'uploaded_at', 'status', 'records_imported']
    list_filter = ['status', 'uploaded_at']
    readonly_fields = ['uploaded_by', 'uploaded_at', 'status', 'records_imported', 'error_message']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)
        
        if not change and obj.file:
            self.process_excel_file(request, obj)
    
    def process_excel_file(self, request, upload_obj):
        try:
            upload_obj.status = 'processing'
            upload_obj.save()
            
            file_path = upload_obj.file.path
            
            from django.core.management import call_command
            from io import StringIO
            import sys
            
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                call_command('import_excel', file_path, '--clear')
                output = captured_output.getvalue()
                
                import re
                imported_matches = re.findall(r'Successfully imported (\d+) total records', output)
                if imported_matches:
                    upload_obj.records_imported = int(imported_matches[0])
                
                upload_obj.status = 'completed'
                messages.success(request, f'Excel file processed successfully! Imported {upload_obj.records_imported} records.')
                
            except Exception as e:
                upload_obj.status = 'error'
                upload_obj.error_message = str(e)
                messages.error(request, f'Error processing Excel file: {str(e)}')
            finally:
                sys.stdout = old_stdout
                upload_obj.save()
                
        except Exception as e:
            upload_obj.status = 'error'
            upload_obj.error_message = str(e)
            upload_obj.save()
            messages.error(request, f'Error processing Excel file: {str(e)}')


admin.site.register(Class)
admin.site.register(Subclass)
admin.site.register(Treatment)
admin.site.register(Reference)
admin.site.register(Compound, CompoundAdmin)
admin.site.register(ExcelUpload, ExcelUploadAdmin)