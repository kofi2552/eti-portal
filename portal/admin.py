from django.contrib import admin
from .models import ErrorLog, SystemLog

@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'method', 'path', 'short_error')
    list_filter = ('method', 'timestamp', 'user')
    search_fields = ('path', 'error_message', 'stack_trace')
    readonly_fields = ('user', 'path', 'method', 'error_message', 'stack_trace', 'timestamp')

    def short_error(self, obj):
        return obj.error_message[:50]
    short_error.short_description = 'Error Message'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'category', 'short_message')
    list_filter = ('category', 'timestamp')
    search_fields = ('message', 'meta')
    readonly_fields = ('user', 'category', 'message', 'meta', 'timestamp')
    autocomplete_fields = ['user'] if hasattr(SystemLog, 'user') else []
    
    def short_message(self, obj):
        return obj.message[:50]
    short_message.short_description = 'Message'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
