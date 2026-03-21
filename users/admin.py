from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.urls import path, reverse
from django.utils.html import format_html
from django.shortcuts import redirect
from django.contrib.auth import login
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active', 'login_as_button')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = (
        (None, {'fields': ('username', 'password', 'role')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'role', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('username', 'email')
    ordering = ('username',)

    def login_as_button(self, obj):
        return format_html(
            '<a class="button" style="background-color: #417690; color: white; padding: 4px 10px; border-radius: 4px; font-weight: bold; text-decoration: none;" href="{}">Login As</a>',
            reverse('admin:login_as_user', args=[obj.pk])
        )
    login_as_button.short_description = 'Impersonate'
    login_as_button.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:user_id>/login-as/', self.admin_site.admin_view(self.login_as_view), name='login_as_user'),
        ]
        return custom_urls + urls

    def login_as_view(self, request, user_id):
        if not request.user.is_superuser:
            return redirect('admin:index')
            
        target_user = self.get_object(request, str(user_id))
        if target_user:
            impersonator_id = request.user.id
            target_user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, target_user)
            request.session['impersonator_id'] = impersonator_id
            
            role = target_user.role
            if role == 'student':
                return redirect('student_main')
            elif role == 'lecturer':
                return redirect('lecturer_main')
            elif role == 'dean':
                return redirect('dean_main')
            elif role in ['admin', 'superadmin', 'finance']:
                return redirect('admin_main')
                
        return redirect('admin:users_customuser_changelist')

admin.site.register(CustomUser, CustomUserAdmin)
