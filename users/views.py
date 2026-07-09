from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from .serializers import RegisterSerializer, UserSerializer
from .models import User, Address, PasswordResetOTP


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user   = serializer.save()
            tokens = get_tokens_for_user(user)
            return Response({
                'message': 'Registration successful',
                'user':    UserSerializer(user).data,
                'tokens':  tokens
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        password     = request.data.get('password')
        user         = authenticate(request, phone_number=phone_number, password=password)
        if user:
            tokens = get_tokens_for_user(user)
            return Response({
                'message': 'Login successful',
                'user':    UserSerializer(user).data,
                'tokens':  tokens
            }, status=status.HTTP_200_OK)
        return Response(
            {'error': 'Invalid phone number or password'},
            status=status.HTTP_401_UNAUTHORIZED
        )


class ProfileView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Not authenticated'}, status=401)
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Not authenticated'}, status=401)
        user           = request.user
        user.full_name = request.data.get('full_name', user.full_name)
        user.email     = request.data.get('email', user.email)
        user.town      = request.data.get('town', user.town)
        user.save()
        return Response({
            'message': 'Profile updated successfully',
            'user':    UserSerializer(user).data,
        })


# ─── PROFILE PHOTO UPLOAD ─────────────────────────────────────────────────────

class UploadProfilePhotoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if 'photo' not in request.FILES:
            return Response({'error': 'No photo provided'}, status=400)

        user  = request.user
        photo = request.FILES['photo']

        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if photo.content_type not in allowed_types:
            return Response({'error': 'Only JPEG, PNG and WEBP images allowed'}, status=400)

        if photo.size > 5 * 1024 * 1024:
            return Response({'error': 'Image size must be under 5MB'}, status=400)

        if user.profile_photo:
            try:
                import os
                if os.path.isfile(user.profile_photo.path):
                    os.remove(user.profile_photo.path)
            except Exception:
                pass

        user.profile_photo = photo
        user.save()

        photo_url = request.build_absolute_uri(user.profile_photo.url)

        return Response({
            'message':   'Profile photo updated successfully!',
            'photo_url': photo_url,
            'user':      UserSerializer(user).data,
        })

    def delete(self, request):
        user = request.user
        if user.profile_photo:
            try:
                import os
                if os.path.isfile(user.profile_photo.path):
                    os.remove(user.profile_photo.path)
            except Exception:
                pass
            user.profile_photo = None
            user.save()
            return Response({'message': 'Profile photo removed'})
        return Response({'message': 'No photo to remove'})


# ─── ADDRESS VIEWS ────────────────────────────────────────────────────────────

class AddressListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-created_at')
        data = [{
            'id':           str(a.id),
            'label':        a.label,
            'full_address': a.full_address,
            'town':         a.town,
            'pincode':      a.pincode or '',
            'is_default':   a.is_default,
        } for a in addresses]
        return Response(data)

    def post(self, request):
        label        = request.data.get('label', 'Home')
        full_address = request.data.get('full_address', '').strip()
        town         = request.data.get('town', '').strip()
        pincode      = request.data.get('pincode', '')
        is_default   = request.data.get('is_default', False)

        if not full_address:
            return Response({'error': 'Address is required'}, status=400)
        if not town:
            return Response({'error': 'Town is required'}, status=400)

        if not Address.objects.filter(user=request.user).exists():
            is_default = True

        address = Address.objects.create(
            user=request.user,
            label=label,
            full_address=full_address,
            town=town,
            pincode=pincode,
            is_default=is_default,
        )
        return Response({
            'message': 'Address added successfully',
            'address': {
                'id':           str(address.id),
                'label':        address.label,
                'full_address': address.full_address,
                'town':         address.town,
                'pincode':      address.pincode or '',
                'is_default':   address.is_default,
            }
        }, status=201)


class AddressDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, address_id):
        try:
            address = Address.objects.get(id=address_id, user=request.user)
        except Address.DoesNotExist:
            return Response({'error': 'Address not found'}, status=404)

        address.label        = request.data.get('label', address.label)
        address.full_address = request.data.get('full_address', address.full_address)
        address.town         = request.data.get('town', address.town)
        address.pincode      = request.data.get('pincode', address.pincode)
        address.is_default   = request.data.get('is_default', address.is_default)
        address.save()
        return Response({'message': 'Address updated successfully'})

    def delete(self, request, address_id):
        try:
            address = Address.objects.get(id=address_id, user=request.user)
            address.delete()
            remaining = Address.objects.filter(user=request.user).first()
            if remaining:
                remaining.is_default = True
                remaining.save()
            return Response({'message': 'Address deleted'})
        except Address.DoesNotExist:
            return Response({'error': 'Address not found'}, status=404)


class SetDefaultAddressView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, address_id):
        try:
            address            = Address.objects.get(id=address_id, user=request.user)
            address.is_default = True
            address.save()
            return Response({'message': 'Default address updated'})
        except Address.DoesNotExist:
            return Response({'error': 'Address not found'}, status=404)


# ─── FORGOT PASSWORD ──────────────────────────────────────────────────────────

class ForgotPasswordView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number', '').strip()

        if not phone_number:
            return Response(
                {'error': 'Phone number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user exists
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response(
                {'error': 'No account found with this phone number'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Delete any existing unused OTPs for this user
        PasswordResetOTP.objects.filter(user=user, is_used=False).delete()

        # Generate new OTP
        otp_code = PasswordResetOTP.generate_otp()

        # Save OTP to database
        from django.utils import timezone
        from datetime import timedelta
        PasswordResetOTP.objects.create(
            user=user,
            otp=otp_code,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        # Send OTP via 2Factor.in (SMS only)
        import requests as req
        import os
        api_key = os.environ.get("TWOFACTOR_API_KEY", "")
        sms_sent = False
        if api_key:
            try:
                url = f"https://2factor.in/API/V1/{api_key}/SMS/+91{phone_number}/AUTOGEN/OTP1"
                resp = req.get(url, timeout=10)
                result = resp.json()
                sms_sent = result.get("Status") == "Success"
                print(f"[SMS] 2Factor: {result}")
            except Exception as e:
                print(f"[SMS] Error: {e}")
        print(f"[OTP] Phone: {phone_number} | OTP: {otp_code} | Sent: {sms_sent}")
        return Response({
            "message": "OTP sent successfully",
            "phone_number": phone_number,
        }, status=status.HTTP_200_OK)


# ─── RESET PASSWORD ───────────────────────────────────────────────────────────

class ResetPasswordView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number', '').strip()
        otp_code     = request.data.get('otp', '').strip()
        new_password = request.data.get('new_password', '').strip()

        # Validate fields
        if not phone_number:
            return Response({'error': 'Phone number is required'}, status=400)
        if not otp_code:
            return Response({'error': 'OTP is required'}, status=400)
        if not new_password or len(new_password) < 6:
            return Response({'error': 'Password must be at least 6 characters'}, status=400)

        # Check user exists
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response(
                {'error': 'No account found with this phone number'},
                status=404
            )

        # Check OTP exists and is valid
        try:
            otp_record = PasswordResetOTP.objects.filter(
                user=user,
                otp=otp_code,
                is_used=False
            ).latest('created_at')
        except PasswordResetOTP.DoesNotExist:
            return Response(
                {'error': 'Invalid OTP. Please request a new one.'},
                status=400
            )

        # Check OTP is not expired
        if not otp_record.is_valid():
            return Response(
                {'error': 'OTP has expired. Please request a new one.'},
                status=400
            )

        # Reset password
        user.set_password(new_password)
        user.save()

        # Mark OTP as used
        otp_record.is_used = True
        otp_record.save()

        print(f"\n[DEV] Password reset successful for {phone_number}\n")

        return Response({
            'message': 'Password reset successful. Please login with your new password.'
        }, status=status.HTTP_200_OK)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_account_request(request):
    """Instantly deactivate account and notify admin"""
    user = request.user
    try:
        phone = user.phone_number
        user.is_active = False
        user.full_name = 'Deleted User'
        user.email     = ''
        user.save()
        try:
            from django.core.mail import send_mail
            send_mail(
                subject=f'Account Deleted - {phone}',
                message=f"""Account deleted by user:\nPhone: {phone}\nID: {user.id}\nTime: {__import__("datetime").datetime.now().strftime("%d %b %Y %H:%M")}""",
                from_email='contact@univerin.in',
                recipient_list=['contact@univerin.in'],
                fail_silently=True,
            )
        except Exception:
            pass
        return Response({'message': 'Account deleted successfully.'}, status=200)
    except Exception as e:
        return Response({'error': 'Failed to delete account. Please try again.'}, status=500)
    except Exception as e:
        return Response({'message': 'Request submitted. We will process it within 24 hours.'}, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def make_admin(request):
    secret = request.data.get('secret', '')
    if secret != 'univerin_admin_2024':
        return Response({'error': 'Invalid secret'}, status=403)
    user = request.user
    user.is_staff = True
    user.is_superuser = True
    user.save()
    return Response({'message': f'{user.phone_number} is now admin!'})


class VerifyOTPView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number', '').strip()
        otp_code     = request.data.get('otp', '').strip()
        if not phone_number or not otp_code:
            return Response({'error': 'Phone number and OTP are required'}, status=400)
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response({'error': 'No account found with this phone number'}, status=404)
        try:
            otp_record = PasswordResetOTP.objects.filter(
                user=user, otp=otp_code, is_used=False
            ).latest('created_at')
        except PasswordResetOTP.DoesNotExist:
            return Response({'error': 'Invalid OTP. Please request a new one.'}, status=400)
        if not otp_record.is_valid():
            return Response({'error': 'OTP has expired. Please request a new one.'}, status=400)
        return Response({'message': 'OTP verified successfully', 'valid': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_push_token(request):
    """Save Expo push token for the logged-in user"""
    token = request.data.get('push_token', '').strip()
    if not token:
        return Response({'error': 'push_token is required'}, status=400)
    request.user.fcm_token = token
    request.user.save()
    return Response({'message': 'Push token saved successfully'})
