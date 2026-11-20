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

        from users.models import AccountDeletionRequest

        if AccountDeletionRequest.objects.filter(
            user=user,
            status__in=["processing", "completed"],
        ).exists():
            raise AuthenticationFailed(
                "This account has a deletion request and cannot access the app.",
                code="account_deletion_processing",
            )

        return user
