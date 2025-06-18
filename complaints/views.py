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
from datetime import timedelta, time
from dateutil.parser import parse

# Create your views here.
class RoomViewSet(GenericViewSet, ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin,DestroyModelMixin):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    pagination_class = CustomLimitOffsetPagination
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
    pagination_class = CustomLimitOffsetPagination
    lookup_field = 'department_code'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['department_name','status']
    search_fields = ['department_code', 'department_name']

class IssueCatViewset(GenericViewSet, ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin):
    queryset = Issue_Category.objects.all()
    serializer_class = IssueCatSerializer
    pagination_class = CustomLimitOffsetPagination
    lookup_field = 'issue_category_code'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['issue_category_code', 'department', 'issue_category_name', 'status']
    search_fields = ['issue_category_code', 'department__department_name', 'issue_category_name']

class ComplaintViewSet(GenericViewSet, ListModelMixin, CreateModelMixin, RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin):
    queryset = Complaint.objects.all().order_by('-submitted_at')
    lookup_field = 'ticket_id'
    pagination_class = CustomLimitOffsetPagination
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
    pagination_class = CustomLimitOffsetPagination
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

        # If no results found before pagination, return empty response with message
        if not stats.exists():
            return Response({
                'message': 'No data found for the specified filters',
                'filters_applied': {
                    'priority': priority,
                    'department': department,
                    'status': status,
                    'submitted_at': submitted_at
                }
            }, status=status.HTTP_200_OK)

        # Paginate the results
        page = self.paginate_queryset(stats)
        if page is not None:
            # The stats are already in the desired dictionary format due to .values() and .annotate()
            # No need to serialize further. Just return the paginated response.
            return self.get_paginated_response(list(page)) # Convert to list to ensure it's iterable

        # Fallback for when pagination is not applied (shouldn't happen with pagination_class set)
        return Response(stats)

    def get_queryset(self):
        queryset = super().get_queryset()
        # You can add additional filtering or aggregation here if needed
        return queryset
    
class TATViewSet(GenericViewSet, ListModelMixin):
    queryset = Complaint.objects.all()
    serializer_class = TATserializer
    pagination_class = CustomLimitOffsetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['priority', 'status']

    @action(detail=False, methods=['get'])
    def all_department_TATS(self, request):
        # Get filter parameters
        priority = request.query_params.get('priority')
        date = request.query_params.get('date')  # Format: YYYY-MM-DD
        start_time = request.query_params.get('start_time')  # Format: HH:MM (24-hour)
        end_time = request.query_params.get('end_time')  # Format: HH:MM (24-hour)

        # Start with base queryset
        queryset = self.queryset

        # Apply priority filter if provided
        if priority:
            if priority not in dict(Complaint.PRIORITY_CHOICES):
                return Response(
                    {'error': 'Invalid priority value'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(priority=priority)

        # Handle date and time filtering
        try:
            if date:
                # Parse the date
                parsed_date = parse(date)
                if not parsed_date:
                    raise ValueError("Invalid date format")

                # If time range is provided
                if start_time or end_time:
                    # Validate time format
                    if start_time:
                        try:
                            # Parse start time
                            start_hour, start_minute = map(int, start_time.split(':'))
                            if not (0 <= start_hour <= 23 and 0 <= start_minute <= 59):
                                raise ValueError("Invalid time format")
                            start_datetime = parsed_date.replace(hour=start_hour, minute=start_minute)
                        except ValueError:
                            raise ValueError("Invalid start time format. Use HH:MM (24-hour)")
                    else:
                        # If no start time, use start of day
                        start_datetime = parsed_date.replace(hour=0, minute=0)

                    if end_time:
                        try:
                            # Parse end time
                            end_hour, end_minute = map(int, end_time.split(':'))
                            if not (0 <= end_hour <= 23 and 0 <= end_minute <= 59):
                                raise ValueError("Invalid time format")
                            end_datetime = parsed_date.replace(hour=end_hour, minute=end_minute)
                        except ValueError:
                            raise ValueError("Invalid end time format. Use HH:MM (24-hour)")
                    else:
                        # If no end time, use end of day
                        end_datetime = parsed_date.replace(hour=23, minute=59)

                    # Apply datetime range filter
                    queryset = queryset.filter(
                        submitted_at__gte=start_datetime,
                        submitted_at__lte=end_datetime
                    )
                else:
                    # If no time range, filter for the entire day
                    queryset = queryset.filter(submitted_at__date=parsed_date)
            elif start_time or end_time:
                # Only time filtering, across all dates
                if start_time:
                    start_hour, start_minute = map(int, start_time.split(':'))
                    start_time_obj = time(start_hour, start_minute)
                else:
                    start_time_obj = time(0, 0)
                if end_time:
                    end_hour, end_minute = map(int, end_time.split(':'))
                    end_time_obj = time(end_hour, end_minute)
                else:
                    end_time_obj = time(23, 59)
                queryset = queryset.filter(
                    submitted_at__time__gte=start_time_obj,
                    submitted_at__time__lte=end_time_obj
                )
        except ValueError as e:
            return Response({
                'error': str(e),
                'message': 'Please use the following formats:',
                'example': {
                    'date_only': '/api/tat/all_department_TATS/?date=2025-06-16',
                    'with_time_range': '/api/tat/all_department_TATS/?date=2025-06-16&start_time=09:00&end_time=17:00'
                },
                'format_guide': {
                    'date': 'YYYY-MM-DD (e.g., 2025-06-16)',
                    'time': 'HH:MM in 24-hour format (e.g., 09:00, 17:30)'
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # Calculate TAT for resolved tickets
        resolved_tickets = queryset.filter(
            status='resolved',
            resolved_at__isnull=False
        ).annotate(
            tat=ExpressionWrapper(
                F('resolved_at') - F('submitted_at'),
                output_field=DurationField()
            )
        )

        # Get total tickets count
        total_tickets = queryset.count()
        
        # Calculate average TAT for resolved tickets
        avg_tat = resolved_tickets.aggregate(
            avg_tat=Avg('tat')
        )['avg_tat']

        # Add individual ticket TATs
        # for ticket in queryset:
        #     ticket_data = {
        #         'ticket_id': ticket.ticket_id,
        #         'submitted_at': ticket.submitted_at,
        #         'resolved_at': ticket.resolved_at,
        #         'priority': ticket.priority,
        #         'status': ticket.status,
        #         'tat': str(ticket.resolved_at - ticket.submitted_at) if ticket.status == 'resolved' and ticket.resolved_at else '-'
        #     }
        #     response_data['tickets'].append(ticket_data)

        # Paginate the queryset for the 'tickets' list
        page = self.paginate_queryset(queryset)

        if page is not None:
            # Serialize the paginated data
            serializer = self.get_serializer(page, many=True)
            paginated_tickets_data = serializer.data

            # Get pagination links and count from self.paginator
            paginator = self.paginator
            count = paginator.count
            next_link = paginator.get_next_link()
            previous_link = paginator.get_previous_link()

            response_data = {
                'total_tickets': total_tickets,
                'average_tat': str(avg_tat) if avg_tat else '-',
                'filters_applied': {
                    'priority': priority,
                    'date': date,
                    'start_time': start_time,
                    'end_time': end_time
                },
                'count': count,
                'next': next_link,
                'previous': previous_link,
                'results': paginated_tickets_data
            }
            return Response(response_data)
        else:
            # Fallback if pagination is not applied (should ideally not be reached if pagination_class is set).
            # In this case, just return the unpaginated results along with aggregations.
            serializer = self.get_serializer(queryset, many=True)
            response_data = {
                'total_tickets': total_tickets,
                'average_tat': str(avg_tat) if avg_tat else '-',
                'filters_applied': {
                    'priority': priority,
                    'date': date,
                    'start_time': start_time,
                    'end_time': end_time
                },
                'results': serializer.data  # Unpaginated results
            }
            return Response(response_data)