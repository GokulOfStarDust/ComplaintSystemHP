from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin,DestroyModelMixin
from django_filters.rest_framework import DjangoFilterBackend
from .models import Room, Complaint
from .serializers import RoomSerializer, ComplaintSerializer, ComplaintCreateSerializer

# Create your views here.
class RoomViewSet(GenericViewSet, ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin,DestroyModelMixin):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'ward', 'speciality', 'room_type']
    search_fields = ['room_no', 'bed_no', 'Block']

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        room = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(Room.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        room.status = new_status
        room.save()
        return Response(RoomSerializer(room).data)

class ComplaintViewSet(GenericViewSet, ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin):
    queryset = Complaint.objects.all().order_by('-submitted_at')
    lookup_field = 'ticket_id'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'issue_type', 'ward', 'block']
    search_fields = ['ticket_id', 'room_number', 'bed_number', 'description']
    ordering_fields = ['submitted_at', 'priority', 'status']
    ordering = ['-submitted_at']  # default ordering
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ComplaintCreateSerializer
        return ComplaintSerializer

    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user.username if self.request.user.is_authenticated else "Anonymous")

    @action(detail=True, methods=['post'])
    def update_status(self, request, ticket_id=None):
        complaint = self.get_object()
        new_status = request.data.get('status')
        remarks = request.data.get('remarks', '')

        if new_status not in dict(Complaint.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        update_data = {
            'status': new_status,
            'remarks': remarks
        }

        if new_status == 'resolved':
            update_data.update({
                'resolved_by': request.user.username if request.user.is_authenticated else None,
                'resolved_at': timezone.now()
            })

        serializer = self.get_serializer(complaint, data=update_data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_status(self, request):
        status_filter = request.query_params.get('status')
        if status_filter not in dict(Complaint.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        complaints = self.queryset.filter(status=status_filter)
        serializer = self.get_serializer(complaints, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_priority(self, request):
        priority_filter = request.query_params.get('priority')
        if priority_filter not in dict(Complaint.PRIORITY_CHOICES):
            return Response(
                {'error': 'Invalid priority'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        complaints = self.queryset.filter(priority=priority_filter)
        serializer = self.get_serializer(complaints, many=True)
        return Response(serializer.data)
