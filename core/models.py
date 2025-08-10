import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Class(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    name = models.CharField("Name", max_length=1024, unique=True, null=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Subclass(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    name = models.CharField("Name", max_length=1024, unique=True, null=False)
    clas = models.ForeignKey(
        "core.Class", verbose_name="Class", null=False, on_delete=models.CASCADE
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Treatment(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    name = models.CharField("Name", max_length=1024, unique=True, null=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


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
    molecule_image = models.ImageField("Molecule Image", upload_to="molecules/", blank=True, null=True)
    # qsar = ???

    class Meta:
        ordering = ["name"]

    def __str__(self):
        if self.origin is None:
            return f"{self.name}"
        return f"{self.name} ({self.origin})"


class ExcelUpload(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, unique=True, editable=False
    )
    file = models.FileField("Excel File", upload_to="excel_uploads/")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
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
    clear_existing_data = models.BooleanField("Clear Existing Data", default=False, help_text="Clear all existing data before importing")

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.file.name} - {self.status}"
