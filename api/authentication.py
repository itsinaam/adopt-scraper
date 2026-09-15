from rest_framework.authentication import TokenAuthentication as BaseTokenAuth


class FlexibleTokenAuthentication(BaseTokenAuth):
    """
    Extends TokenAuthentication to seamlessly support:
    - Authorization: Token <key>
    - Authorization: Bearer <key>
    - Authorization: <key> (when pasted directly in Swagger UI or API tools)
    """
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "").strip()
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) == 1:
            # Token pasted directly without 'Token' prefix
            token_key = parts[0]
            return self.authenticate_credentials(token_key)
        elif len(parts) == 2 and parts[0].lower() in ["token", "bearer"]:
            return self.authenticate_credentials(parts[1])

        return super().authenticate(request)


from drf_spectacular.extensions import OpenApiAuthenticationExtension


class FlexibleTokenScheme(OpenApiAuthenticationExtension):
    target_class = "api.authentication.FlexibleTokenAuthentication"
    name = "Bearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
        }

