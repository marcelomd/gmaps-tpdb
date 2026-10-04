import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.normalize import clean, norm_key

User = get_user_model()


class KeyedName(models.Model):
    """A name whose identity is its case-insensitive key, not its spelling

    The spelling that was stored first stays as the display name; later spellings
    that differ only in case or whitespace resolve to the same row.
    """

    key = models.CharField(max_length=1024, editable=False, default="")

    class Meta:
        abstract = True

    def key_scope(self):
        """Rows this one must be unique among"""
        return type(self).objects.all()

    def save(self, *args, **kwargs):
        self.name = clean(self.name)
        self.key = norm_key(self.name)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.name and self.key_scope().filter(key=norm_key(self.name)).exclude(pk=self.pk).exists():
            raise ValidationError(
                {"name": "Another entry already has this name (letter case is ignored)."}
            )


class Class(KeyedName):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    name = models.CharField("Name", max_length=1024, unique=True, null=False)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["key"], name="unique_class_key")]
        verbose_name_plural = "classes"

    def __str__(self):
        return self.name


class Subclass(KeyedName):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    name = models.CharField("Name", max_length=1024, null=False)
    clas = models.ForeignKey(
        "core.Class", verbose_name="Class", null=False, on_delete=models.CASCADE
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["clas", "name"], name="unique_subclass_per_class"),
            models.UniqueConstraint(fields=["clas", "key"], name="unique_subclass_key_per_class"),
        ]

    def key_scope(self):
        return Subclass.objects.filter(clas_id=self.clas_id)

    def __str__(self):
        return self.name


class Treatment(KeyedName):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    name = models.CharField("Name", max_length=1024, unique=True, null=False)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["key"], name="unique_treatment_key")]

    def __str__(self):
        return self.name


class Alias(models.Model):
    """Another spelling (synonym, typo, acronym) that resolves to an existing entry

    Aliases are recorded when an admin merges two entries, so later uploads that
    use the old spelling land on the surviving entry instead of recreating it.
    """

    key = models.CharField("Alias", max_length=1024)

    class Meta:
        abstract = True

    def target_scope(self):
        """Entries the alias key must not collide with"""
        raise NotImplementedError

    def save(self, *args, **kwargs):
        self.key = norm_key(self.key)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not self.target_id:
            return
        key = norm_key(self.key)
        if self.target_scope().filter(key=key).exists():
            raise ValidationError({"key": "An entry with this name already exists."})
        if type(self).objects.filter(key=key, **self.alias_scope()).exclude(pk=self.pk).exists():
            raise ValidationError({"key": "This alias already exists."})

    def alias_scope(self):
        return {}

    def __str__(self):
        return f"{self.key} → {self.target}"


class ClassAlias(Alias):
    target = models.ForeignKey(Class, on_delete=models.CASCADE, related_name="aliases")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key"], name="unique_class_alias")]
        verbose_name_plural = "class aliases"

    def target_scope(self):
        return Class.objects.all()


class SubclassAlias(Alias):
    target = models.ForeignKey(Subclass, on_delete=models.CASCADE, related_name="aliases")
    clas = models.ForeignKey(Class, on_delete=models.CASCADE, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["clas", "key"], name="unique_subclass_alias")
        ]
        verbose_name_plural = "subclass aliases"

    def save(self, *args, **kwargs):
        self.clas_id = self.target.clas_id
        super().save(*args, **kwargs)

    def target_scope(self):
        return Subclass.objects.filter(clas_id=self.target.clas_id)

    def alias_scope(self):
        return {"clas_id": self.target.clas_id}


class TreatmentAlias(Alias):
    target = models.ForeignKey(Treatment, on_delete=models.CASCADE, related_name="aliases")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key"], name="unique_treatment_alias")]
        verbose_name_plural = "treatment aliases"

    def target_scope(self):
        return Treatment.objects.all()


class Reference(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    value = models.CharField("Value", max_length=1024)

    class Meta:
        ordering = ["value"]

    def __str__(self):
        return f"{self.value}"


class FormulaMass(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    formula = models.CharField("Formula [M+H]", max_length=1024, null=False)
    mass = models.CharField("m/z")

    def __str__(self):
        return f"{self.formula}, {self.mass}"


class Compound(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    origin = models.ForeignKey(
        "core.Compound", verbose_name="Origin", null=True, on_delete=models.CASCADE
    )
    clas = models.ForeignKey(
        "core.Class", verbose_name="Class", null=False, on_delete=models.CASCADE
    )
    subclass = models.ForeignKey(
        "core.Subclass", verbose_name="Subclass", null=False, on_delete=models.CASCADE
    )
    treatment = models.ManyToManyField(Treatment)
    references = models.ManyToManyField(Reference)
    formulas = models.ManyToManyField(FormulaMass)
    type = models.CharField("Type", max_length=8, null=False)
    mode = models.BooleanField("Mode", null=False)
    name = models.CharField("Name", max_length=1024, null=False)
    neutral_formula = models.CharField("Neutral Formula", max_length=1024, null=False)
    mz_ion = models.CharField("m/z Ion", max_length=1024, null=False)
    smile = models.CharField("SMILE", max_length=1024, null=False)
    molecule_image = models.ImageField(
        "Molecule Image", upload_to="molecules/", blank=True, null=True
    )
    notes = models.CharField("Notes", max_length=2048, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        if self.origin is None:
            return f"{self.name}"
        return f"{self.name} ({self.origin})"


class DeletedUserSnapshot(models.Model):
    """Identity kept on rows whose user FK is nulled when the user is deleted"""

    former_user_email = models.EmailField("Former user email", blank=True)
    former_user_name = models.CharField("Former user name", max_length=300, blank=True)

    class Meta:
        abstract = True

    def user_label(self, user):
        if user:
            return user.email
        if self.former_user_email:
            return f"{self.former_user_email} (deleted)"
        return "deleted user"


class ExcelUpload(DeletedUserSnapshot):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    file = models.FileField("Excel File", upload_to="excel_uploads/")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("error", "Error"),
        ],
        default="pending",
    )
    records_imported = models.IntegerField("Records Imported", default=0)
    error_message = models.TextField("Error Message", blank=True, null=True)
    clear_existing_data = models.BooleanField(
        "Clear Existing Data",
        default=False,
        help_text="Clear all existing data before importing",
    )
    report = models.JSONField(
        "Import report",
        blank=True,
        null=True,
        help_text="New names created by this import and any that look like existing ones",
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.file.name} - {self.status}"


class UserEvent(DeletedUserSnapshot):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    user = models.ForeignKey(
        User, verbose_name="User", on_delete=models.SET_NULL, null=True
    )
    event_type = models.CharField(
        "Event Type",
        max_length=20,
        choices=[
            ("view", "View"),
            ("login", "Login"),
            ("register", "Register"),
            ("query", "Query"),
            ("import", "Import"),
        ],
    )
    timestamp = models.DateTimeField("Timestamp", auto_now_add=True)
    extra_data = models.JSONField("Extra Data", blank=True, null=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user_label(self.user)} - {self.event_type} - {self.timestamp}"
