from django.db import models
import qrcode
from io import BytesIO
from django.core.files import File
from PIL import Image
import uuid
import base64
import json
import hmac
import hashlib
from django.conf import settings

# Create your models here.
class Room(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]
    
    bed_no = models.CharField(max_length=10)
    room_no = models.CharField(max_length=20)
    Block = models.CharField(max_length=10)
    Floor_no = models.IntegerField()
    ward = models.CharField(max_length=20)
    speciality = models.CharField(max_length=20)
    room_type = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='inactive')
    
    # QR Code
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    dataenc = models.CharField(max_length=500, blank=True, null=True)  # Store base64 encoded data
    
    def __str__(self):
        return f"Room {self.room_no} - Bed {self.bed_no} - {self.Block}"
    
    def get_room_data(self):
        # Create a dictionary of room data
        room_data = {
            'bed_no': self.bed_no,
            'room_no': self.room_no,
            'Block': self.Block,
            'Floor_no': self.Floor_no,
            'ward': self.ward,
            'speciality': self.speciality,
            'room_type': self.room_type,
            'status': self.status
        }
        # Convert to JSON string and then to base64
        json_data = json.dumps(room_data)
        return base64.b64encode(json_data.encode()).decode()
    
    def save(self, *args, **kwargs):
        # Generate base64 encoded data
        self.dataenc = self.get_room_data()
        
        # Generate HMAC signature
        signature = hmac.new(
            settings.QR_CODE_SECRET_KEY.encode('utf-8'),
            self.dataenc.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        # Add the URL with encoded data and signature
        qr_data = f"http://localhost:5173/ComplaintForm?data={self.dataenc}&signature={signature}"
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR code to model
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        filename = f'qr_code_{self.room_no}_{self.bed_no}.png'
        self.qr_code.save(filename, File(buffer), save=False)
        
        super().save(*args, **kwargs)


class Complaint(models.Model):
    PRIORITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')]
    STATUS_CHOICES = [('open', 'Open'), ('in_progress', 'In_Progress'), ('resolved', 'Resolved'),('closed','Closed'),('on_hold','On_Hold')]

    # Make ticket_id the primary key
    ticket_id = models.CharField(max_length=12, primary_key=True, editable=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Room details (copied, not related)
    bed_number = models.CharField(max_length=20)
    block = models.CharField(max_length=50)
    room_number = models.CharField(max_length=20)
    floor = models.CharField(max_length=20)
    ward = models.CharField(max_length=50)
    speciality = models.CharField(max_length=100)
    room_type = models.CharField(max_length=50)
    room_status = models.CharField(max_length=10)

    # Patient input fields
    issue_type = models.CharField(max_length=50)  # This will store the issue_category_name
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES)
    submitted_by = models.CharField(max_length=100, default="Patient")

    # Status tracking
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    assigned_department = models.CharField(max_length=100, blank=True, null=True)
    resolved_by = models.CharField(max_length=100, blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            # Generate ticket ID
            self.ticket_id = "SVN" + str(uuid.uuid4().int)[:5].zfill(5)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket {self.ticket_id} - Room {self.room_number} ({self.ward})"
    

class ComplaintImage(models.Model):
    complaint = models.ForeignKey('Complaint', related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='complaint_images/')

    def __str__(self):
        return f"Image for Complaint {self.complaint.ticket_id}"

class Department(models.Model):
    department_code = models.CharField(max_length=6, primary_key=True)
    department_name = models.CharField(max_length=20, unique=True)
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='inactive')

    def __str__(self):
        return self.department_name
    
class Issue_Category(models.Model):
    issue_category_code = models.CharField(max_length=6,primary_key=True)
    department = models.ForeignKey('Department', related_name='issue_categories', on_delete=models.CASCADE)
    issue_category_name = models.CharField(max_length=20,unique=True)
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='inactive')

    def __str__(self):
        return f"{self.issue_category_name} ({self.department.department_name})"