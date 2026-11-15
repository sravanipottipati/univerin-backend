from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from users.models import AccountDeletionRequest


class ActiveAccountTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)

        if user_id is None:
            raise AuthenticationFailed("Invalid refresh token.")

        User = get_user_model()

        try:
            user = User.objects.get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
        except User.DoesNotExist:
            raise AuthenticationFailed(
                "This account no longer exists."
            )

        if not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                "This account is inactive."
            )

        if getattr(user, "is_deleted", False):
            raise AuthenticationFailed(
                "This account has been deleted."
            )

        if AccountDeletionRequest.objects.filter(
            user=user,
            status__in=["pending", "processing", "completed"],
        ).exists():
            raise AuthenticationFailed(
                "This account has a deletion request."
            )

        return super().validate(attrs)
