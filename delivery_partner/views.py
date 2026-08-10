from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import DeliveryPartner


class DPOnboardingVehicleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_type != 'delivery_partner':
            return Response({'error': 'Not a delivery partner account'}, status=status.HTTP_403_FORBIDDEN)

        vehicle_type = request.data.get('vehicle_type', '').strip()
        vehicle_number = request.data.get('vehicle_number', '').strip()

        if vehicle_type not in ['bike', 'scooter', 'bicycle']:
            return Response({'error': 'Select a valid vehicle type'}, status=status.HTTP_400_BAD_REQUEST)
        if not vehicle_number:
            return Response({'error': 'Vehicle registration number is required'}, status=status.HTTP_400_BAD_REQUEST)

        dp, created = DeliveryPartner.objects.get_or_create(user=request.user)
        dp.vehicle_type = vehicle_type
        dp.vehicle_number = vehicle_number
        dp.save()

        return Response({'message': 'Vehicle details saved', 'status': dp.status}, status=status.HTTP_200_OK)


class DPOnboardingDocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_type != 'delivery_partner':
            return Response({'error': 'Not a delivery partner account'}, status=status.HTTP_403_FORBIDDEN)

        dp, created = DeliveryPartner.objects.get_or_create(user=request.user)

        for field in ['aadhaar_number', 'pan_number', 'driving_licence_number']:
            if field in request.data:
                setattr(dp, field, request.data[field])

        for field in ['aadhaar_document', 'pan_document', 'driving_licence_document', 'selfie_photo']:
            if field in request.FILES:
                setattr(dp, field, request.FILES[field])

        dp.save()
        dp.submit_for_verification()

        return Response({
            'message': 'Documents saved',
            'status': dp.status,
            'has_all_documents': dp.has_all_documents(),
        }, status=status.HTTP_200_OK)


class DPOnboardingStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != 'delivery_partner':
            return Response({'error': 'Not a delivery partner account'}, status=status.HTTP_403_FORBIDDEN)

        try:
            dp = request.user.delivery_partner
        except DeliveryPartner.DoesNotExist:
            return Response({
                'status': 'pending_kyc', 'has_all_documents': False,
                'vehicle_type': None, 'vehicle_number': None,
            }, status=status.HTTP_200_OK)

        return Response({
            'status': dp.status,
            'has_all_documents': dp.has_all_documents(),
            'vehicle_type': dp.vehicle_type,
            'vehicle_number': dp.vehicle_number,
            'rejection_reason': dp.rejection_reason,
        }, status=status.HTTP_200_OK)
class DPDutyToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_type != 'delivery_partner':
            return Response({'error': 'Not a delivery partner account'}, status=status.HTTP_403_FORBIDDEN)

        try:
            dp = request.user.delivery_partner
        except DeliveryPartner.DoesNotExist:
            return Response({'error': 'Complete onboarding first'}, status=status.HTTP_400_BAD_REQUEST)

        if dp.status != 'approved':
            return Response({'error': 'Your account is not yet approved'}, status=status.HTTP_403_FORBIDDEN)

        is_online = request.data.get('is_online', False)
        dp.is_online = bool(is_online)
        dp.save(update_fields=['is_online', 'updated_at'])

        return Response({'message': 'Status updated', 'is_online': dp.is_online}, status=status.HTTP_200_OK)