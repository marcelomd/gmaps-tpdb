from django.contrib.auth import get_user_model
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import ExcelUpload, UserEvent


@receiver(pre_delete, sender=get_user_model())
def preserve_user_identity(sender, instance, **kwargs):
    """Copy who the user was onto their audit rows before the FK is nulled"""
    identity = {
        "former_user_email": instance.email,
        "former_user_name": instance.get_full_name(),
    }
    UserEvent.objects.filter(user=instance).update(**identity)
    ExcelUpload.objects.filter(uploaded_by=instance).update(**identity)
