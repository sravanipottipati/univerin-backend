from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class ActiveAccountJWTAuthentication(JWTAuthentication):
    """
    Reject JWT authentication for accounts marked as deleted.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if getattr(user, "is_deleted", False):
            raise AuthenticationFailed(
                "This account has been deleted.",
                code="account_deleted",
            )

        return user
