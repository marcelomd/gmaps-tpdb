import tempfile
import uuid
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from .excel import is_positive
from .models import Class, Compound, ExcelUpload, Subclass, UserEvent


class AuthenticatedTestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user("user@example.com", first_name="Ann", last_name="Lee")
        self.client.force_login(self.user)


class MoleculeImageTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        (Path(self.media.name) / "molecules").mkdir()
        (Path(self.media.name) / "excel_uploads").mkdir()
        self.name = f"molecule_{uuid.uuid4()}.png"
        (Path(self.media.name) / "molecules" / self.name).write_bytes(b"png")
        (Path(self.media.name) / "excel_uploads" / "secret.xlsx").write_bytes(b"data")

    def get(self, filename):
        with override_settings(MEDIA_ROOT=self.media.name):
            return self.client.get(reverse("molecule_image", args=[filename]))

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.get(self.name).status_code, 302)

    def test_serves_image_to_logged_in_user(self):
        response = self.get(self.name)
        self.assertEqual(b"".join(response.streaming_content), b"png")

    def test_other_media_is_not_reachable(self):
        self.assertEqual(self.get("secret.xlsx").status_code, 404)
        self.assertEqual(self.get("..%2Fexcel_uploads%2Fsecret.xlsx").status_code, 404)


class CompoundsApiTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        clas = Class.objects.create(name="Alkaloids")
        sub = Subclass.objects.create(name="Indole", clas=clas)
        self.compound = Compound.objects.create(
            clas=clas, subclass=sub, type="TP", mode=True, name="Foo",
            neutral_formula="C1", mz_ion="1", smile="C",
        )

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("compounds_api")).status_code, 302)

    def test_filters_by_name_and_id(self):
        data = self.client.get(reverse("compounds_api"), {"name": "fo"}).json()
        self.assertEqual(data["pagination"]["total"], 1)
        data = self.client.get(reverse("compounds_api"), {"class_name": "nothing"}).json()
        self.assertEqual(data["pagination"]["total"], 0)

    def test_invalid_uuid_is_rejected(self):
        for param in ("compound_id", "class_id", "subclass_id", "origin_id", "treatment_id"):
            response = self.client.get(reverse("compounds_api"), {param: "nope"})
            self.assertEqual(response.status_code, 400, param)

    def test_internal_errors_do_not_leak_details(self):
        with mock.patch("core.views.Paginator", side_effect=RuntimeError("secret detail")):
            response = self.client.get(reverse("compounds_api"))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret detail", response.content.decode())

    def test_query_is_logged_with_filters(self):
        self.client.get(reverse("compounds_api"), {"name": "fo", "page": 1})
        self.assertEqual(UserEvent.objects.get(event_type="query").extra_data, {"filters": {"name": "fo"}})


class UserDeletionTests(AuthenticatedTestCase):
    def test_events_and_uploads_survive_with_identity(self):
        UserEvent.objects.create(user=self.user, event_type="view")
        ExcelUpload.objects.create(file="x.xlsx", uploaded_by=self.user)
        CustomUser.objects.filter(pk=self.user.pk).delete()

        for row in (UserEvent.objects.get(), ExcelUpload.objects.get()):
            self.assertEqual(row.former_user_email, "user@example.com")
            self.assertEqual(row.former_user_name, "Ann Lee")
            self.assertIn("user@example.com", row.user_label(None))


class ExcelHelperTests(TestCase):
    def test_mode_is_case_insensitive(self):
        self.assertTrue(is_positive("Positive"))
        self.assertTrue(is_positive("positive"))
        self.assertFalse(is_positive("Negative"))
        self.assertFalse(is_positive(""))
