from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin,DestroyModelMixin
from django_filters.rest_framework import DjangoFilterBackend
from .models import Room, Complaint, Department, Issue_Category
from .serializers import RoomSerializer, ComplaintSerializer, ComplaintCreateSerializer, ComplaintUpdateSerializer, DepartmentSerializer,IssueCatSerializer,ReportDepartment,TATserializer
from .pagination import CustomLimitOffsetPagination
from django.db.models import Count, Q
from django.db.models import Avg, F, ExpressionWrapper, DurationField
from datetime import timedelta

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


class DepartmentViewSet(GenericViewSet, ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    lookup_field = 'department_code'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['department_name','status']
    search_fields = ['department_code', 'department_name']

class IssueCatViewset(GenericViewSet, ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin):
    queryset = Issue_Category.objects.all()
    serializer_class = IssueCatSerializer
    lookup_field = 'issue_category_code'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['issue_category_code', 'department', 'issue_category_name', 'status']
    search_fields = ['issue_category_code', 'department__department_name', 'issue_category_name']

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
        elif self.action == 'update' or self.action == 'partial_update':
            return ComplaintUpdateSerializer
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

class ReportViewSet(GenericViewSet, ListModelMixin):
    queryset = Complaint.objects.all()
    serializer_class = ReportDepartment
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['assigned_department', 'priority', 'status', 'submitted_at']

    @action(detail=False, methods=['get'])
    def department_priority_stats(self, request):
        # Get department and priority from query params
        department = request.query_params.get('department')
        priority = request.query_params.get('priority')

        if not department or not priority:
            return Response(
                {'error': 'Both department and priority parameters are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate priority
        if priority not in dict(Complaint.PRIORITY_CHOICES):
            return Response(
                {'error': 'Invalid priority value'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get counts for the specific department and priority
        stats = self.queryset.filter(
            assigned_department=department,
            priority=priority
        ).aggregate(
            open_tickets=Count('ticket_id', filter=Q(status='open')),
            resolved_tickets=Count('ticket_id', filter=Q(status='resolved')),
            total_tickets=Count('ticket_id')
        )

        # Add department and priority to the response
        stats['department'] = department
        stats['priority'] = priority

        return Response(stats)

    @action(detail=False, methods=['get'])
    def all_department_stats(self, request):
        # Get filter parameters
        priority = request.query_params.get('priority')
        department = request.query_params.get('department')
        status = request.query_params.get('status')
        submitted_at = request.query_params.get('submitted_at')

        # Start with base queryset
        queryset = self.queryset

        # Apply filters if provided
        if priority:
            if priority not in dict(Complaint.PRIORITY_CHOICES):
                return Response(
                    {'error': 'Invalid priority value'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(priority=priority)

        if department:
            queryset = queryset.filter(assigned_department=department)

        if status:
            queryset = queryset.filter(status=status)

        if submitted_at:
            queryset = queryset.filter(submitted_at__date=submitted_at)

        # Get all combinations of department and priority with their counts
        stats = queryset.values('assigned_department', 'priority').annotate(
            open_tickets=Count('ticket_id', filter=Q(status='open')),
            resolved_tickets=Count('ticket_id', filter=Q(status='resolved')),
            total_tickets=Count('ticket_id')
        ).order_by('assigned_department', 'priority')

        # If no results found
        if not stats:
            return Response({
                'message': 'No data found for the specified filters',
                'filters_applied': {
                    'priority': priority,
                    'department': department,
                    'status': status,
                    'submitted_at': submitted_at
                }
            })

        return Response(stats)

    def get_queryset(self):
        queryset = super().get_queryset()
        # You can add additional filtering or aggregation here if needed
        return queryset
    
class TATViewSet(GenericViewSet, ListModelMixin):
    queryset = Complaint.objects.all()
    serializer_class = TATserializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['submitted_at','resolved_at','ticket_id', 'priority', 'status']

    @action(detail=False, methods=['get'])
    def all_department_TATS(self, request):
        # Calculate TAT for resolved tickets
        resolved_tickets = self.queryset.filter(
            status='resolved',
            resolved_at__isnull=False
        ).annotate(
            tat=ExpressionWrapper(
                F('resolved_at') - F('submitted_at'),
                output_field=DurationField()
            )
        )

        # Get total tickets count
        total_tickets = self.queryset.count()
        
        # Calculate average TAT for resolved tickets
        avg_tat = resolved_tickets.aggregate(
            avg_tat=Avg('tat')
        )['avg_tat']

        # Format the response data
        response_data = {
            'total_tickets': total_tickets,
            'average_tat': str(avg_tat) if avg_tat else '-',
            'tickets': []
        }

        # Add individual ticket TATs
        for ticket in self.queryset:
            ticket_data = {
                'ticket_id': ticket.ticket_id,
                'submitted_at': ticket.submitted_at,
                'resolved_at': ticket.resolved_at,
                'priority': ticket.priority,
                'status': ticket.status,
                'tat': str(ticket.resolved_at - ticket.submitted_at) if ticket.status == 'resolved' and ticket.resolved_at else '-'
            }
            response_data['tickets'].append(ticket_data)

        return Response(response_data)