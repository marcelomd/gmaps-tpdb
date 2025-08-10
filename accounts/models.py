from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    # Add your custom fields here
        phone_number = models.CharField(max_length=15, blank=True, null=True)
    # You can also change or remove existing fields
    # email = models.EmailField(unique=True) 