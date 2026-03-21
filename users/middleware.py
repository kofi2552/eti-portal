class ImpersonationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            impersonator_id = request.session.get('impersonator_id')
            if impersonator_id:
                request.user.impersonator_id = impersonator_id
        return self.get_response(request)
