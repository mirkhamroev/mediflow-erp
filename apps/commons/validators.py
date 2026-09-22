import re
from django.core.exceptions import ValidationError

def validate_phone_number(value):
    if not re.match(r'^\+?[1-9]\d{1,14}$', value):
        raise ValidationError("Invalid phone number format")
    pass

def validate_email(value):
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
        raise ValidationError("Invalid email number format")