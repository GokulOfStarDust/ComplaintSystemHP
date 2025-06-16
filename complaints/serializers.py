import hmac
import hashlib
from django.conf import settings
from rest_framework import serializers
from .models import Room, Complaint, ComplaintImage, Department,Issue_Category
from django.db import models

class ComplaintImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintImage
        fields = ['image']  # you can also include 'id' if needed

    def to_internal_value(self, data):
        return super().to_internal_value(data)


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'
        read_only_fields = ('qr_code', 'dataenc')

    def validate(self, data):
        # Get all fields except status
        bed_no = data.get('bed_no')
        room_no = data.get('room_no')
        Block = data.get('Block')
        Floor_no = data.get('Floor_no')
        ward = data.get('ward')
        speciality = data.get('speciality')
        room_type = data.get('room_type')

        # Check if all required fields are present
        if all([bed_no, room_no, Block, Floor_no, ward, speciality, room_type]):
            # Check if a room with these exact fields already exists
            existing_room = Room.objects.filter(
                bed_no=bed_no,
                room_no=room_no,
                Block=Block,
                Floor_no=Floor_no,
                ward=ward,
                speciality=speciality,
                room_type=room_type
            )

            # If updating, exclude the current instance from the check
            if self.instance:
                existing_room = existing_room.exclude(pk=self.instance.pk)

            if existing_room.exists():
                raise serializers.ValidationError(
                    "A room with these exact details already exists. All fields (except status) must be unique together."
                )

        return data


class DepartmentSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(required=False)  # Make it optional for updates

    class Meta:
        model = Department
        fields = '__all__'

    def get_fields(self):
        fields = super().get_fields()
        # Make department_code read-only if we're updating an existing instance
        if self.instance is not None:
            fields['department_code'].read_only = True
        return fields

    def validate_department_name(self, value):
        # Ensure department name is unique (case-insensitive)
        if self.instance:  # If updating
            if Department.objects.exclude(pk=self.instance.pk).filter(department_name__iexact=value).exists():
                raise serializers.ValidationError("A department with this name already exists.")
        else:  # If creating
            if Department.objects.filter(department_name__iexact=value).exists():
                raise serializers.ValidationError("A department with this name already exists.")
        return value

    def validate_status(self, value):
        if value not in dict(Department.STATUS_CHOICES):
            raise serializers.ValidationError("Invalid status value")
        return value


class IssueCatSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    issue_category_code = serializers.CharField(required=False)  # Updated field name

    class Meta:
        model = Issue_Category
        fields = '__all__'

    def get_fields(self):
        fields = super().get_fields()
        # Make issue_category_code read-only if we're updating an existing instance
        if self.instance is not None:
            fields['issue_category_code'].read_only = True
        return fields

    def validate_issue_category_name(self, value):  # Updated field name
        # Ensure category name is unique (case-insensitive)
        if self.instance:  # If updating
            if Issue_Category.objects.exclude(pk=self.instance.pk).filter(
                department=self.initial_data.get('department', self.instance.department),
                issue_category_name__iexact=value  # Updated field name
            ).exists():
                raise serializers.ValidationError("An issue category with this name already exists in this department.")
        else:  # If creating
            if Issue_Category.objects.filter(
                department=self.initial_data.get('department'),
                issue_category_name__iexact=value  # Updated field name
            ).exists():
                raise serializers.ValidationError("An issue category with this name already exists in this department.")
        return value

    def validate_status(self, value):
        if value not in dict(Issue_Category.STATUS_CHOICES):
            raise serializers.ValidationError("Invalid status value")
        return value

    def validate_department(self, value):
        if value.status != 'active':
            raise serializers.ValidationError("Cannot assign issue category to an inactive department")
        return value

class ComplaintCreateSerializer(serializers.ModelSerializer):
    images = ComplaintImageSerializer(many=True,write_only=True,required=False)
    
    # Add fields to receive QR data and signature from frontend
    qr_data_from_qr = serializers.CharField(write_only=True, required=False)
    qr_signature_from_qr = serializers.CharField(write_only=True, required=False)

    def create(self, validated_data):
        # Access images directly from request.FILES
        images_data = self.context['request'].FILES.getlist('images')
        # Remove 'images' from validated_data as it's not processed by the serializer field
        validated_data.pop('images', None) 
        
        # Remove QR data and signature as they are for validation only
        validated_data.pop('qr_data_from_qr', None)
        validated_data.pop('qr_signature_from_qr', None)

        complaint = Complaint.objects.create(**validated_data)

        for image_file in images_data:
            ComplaintImage.objects.create(complaint=complaint, image=image_file)

        return complaint

    def validate(self, data):
        # Get the issue type from the data
        issue_type = data.get('issue_type')
        
        # Find the corresponding issue category and get its department
        try:
            issue_category = Issue_Category.objects.get(issue_category_name=issue_type, status='active')
            # Set the assigned department automatically
            data['assigned_department'] = issue_category.department.department_name
        except Issue_Category.DoesNotExist:
            raise serializers.ValidationError({
                'issue_type': 'Invalid or inactive issue category. Please select a valid issue category.'
            })

        # Perform existing room validation
        if any(field in data for field in ['bed_number', 'room_number', 'block', 'floor', 'ward', 'speciality', 'room_type']):
            try:
                room = Room.objects.get(
                    bed_no=data['bed_number'],
                    room_no=data['room_number'],
                    Block=data['block'],
                    Floor_no=data['floor'],
                    ward=data['ward'],
                    speciality=data['speciality'],
                    room_type=data['room_type']
                )
                if room.status != 'active':
                    raise serializers.ValidationError("The specified room is not active")
                # Update room_status to match room's status
                data['room_status'] = room.status
            except Room.DoesNotExist:
                raise serializers.ValidationError("Room not found with the provided details")
        
        # HMAC Verification Logic
        qr_data_from_qr = self.initial_data.get('qr_data_from_qr')
        qr_signature_from_qr = self.initial_data.get('qr_signature_from_qr')

        if qr_data_from_qr and qr_signature_from_qr:
            expected_signature = hmac.new(
                settings.QR_CODE_SECRET_KEY.encode('utf-8'),
                qr_data_from_qr.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_signature, qr_signature_from_qr):
                raise serializers.ValidationError({'qr_code': 'QR code data has been tampered with or is invalid.'})
        elif not qr_data_from_qr and not qr_signature_from_qr and self.context['request'].method == 'POST':
            # If it's a POST request and QR data/signature are missing, it means
            # the request is not coming from a QR scan, so we don't apply this validation.
            pass  # Allow requests without QR data/signature
        else:
            raise serializers.ValidationError({'qr_code': 'QR data or signature missing for QR-based complaint submission.'})

        # New validation: Prevent duplicate open/in-progress complaints for the same issue in the same room
        if issue_type and all(field in data for field in ['bed_number', 'room_number', 'block', 'floor', 'ward', 'speciality', 'room_type']):
            existing_complaint = Complaint.objects.filter(
                issue_type=issue_type,
                bed_number=data['bed_number'],
                room_number=data['room_number'],
                block=data['block'],
                floor=data['floor'],
                ward=data['ward'],
                speciality=data['speciality'],
                room_type=data['room_type'],
                status__in=['open', 'in_progress']  # Check for open or in-progress status
            ).exists()

            if existing_complaint:
                raise serializers.ValidationError(
                    'A complaint with the same issue type is already open or in progress for this room.'
                )

        return data

    class Meta:
        model = Complaint
        fields = '__all__'

   

class ComplaintSerializer(serializers.ModelSerializer):
    images = ComplaintImageSerializer(many=True, read_only=True)
    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = ('ticket_id',)

    def validate(self, data):
        # Only validate room if room-related fields are being updated
        if any(field in data for field in ['bed_number', 'room_number', 'block', 'floor', 'ward', 'speciality', 'room_type']):
            try:
                room = Room.objects.get(
                    bed_no=data['bed_number'],
                    room_no=data['room_number'],
                    Block=data['block'],
                    Floor_no=data['floor'],
                    ward=data['ward'],
                    speciality=data['speciality'],
                    room_type=data['room_type']
                )
                if room.status != 'active':
                    raise serializers.ValidationError("The specified room is not active")
                # Update room_status to match room's status
                data['room_status'] = room.status
            except Room.DoesNotExist:
                raise serializers.ValidationError("Room not found with the provided details")
        return data


class ComplaintUpdateSerializer(serializers.ModelSerializer):
    images = ComplaintImageSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = ('ticket_id',)

    def update(self, instance, validated_data):
        images_data = self.context['request'].FILES.getlist('images')
        validated_data.pop('images', None)

        # Update complaint fields
        complaint = super().update(instance, validated_data)

        # Create new images
        for image_file in images_data:
            ComplaintImage.objects.create(complaint=complaint, image=image_file)

        return complaint

class ComplaintImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintImage
        fields = ['image']

class ReportDepartment(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ['ticket_id', 'assigned_department', 'priority', 'status', 'submitted_at', 'issue_type', 'room_number', 'ward']
class TATserializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ['ticket_id','submitted_at','resolved_at','priority','status']