import traceback
from .models import ErrorLog

class ExceptionLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        
        actual_user = user
        if user and hasattr(user, 'impersonator_id') and user.impersonator_id:
            from users.models import CustomUser
            impersonator = CustomUser.objects.filter(id=user.impersonator_id).first()
            if impersonator:
                actual_user = impersonator

        ErrorLog.objects.create(
            user=actual_user,
            path=request.build_absolute_uri(),
            method=request.method,
            error_message=str(exception),
            stack_trace=traceback.format_exc()
        )
        return None
