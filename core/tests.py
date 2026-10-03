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
        self.client.get(reverse("compounds_api"), {"name": "fo", "page": 1, "junk": "x" * 5000})
        self.assertEqual(UserEvent.objects.get(event_type="query").extra_data, {"filters": {"name": "fo"}})


class UserDeletionTests(AuthenticatedTestCase):
    def test_events_and_uploads_survive_with_identity(self):
        UserEvent.objects.create(user=self.user, event_type="view")
        ExcelUpload.objects.create(file="x.xlsx", uploaded_by=self.user)
        CustomUser.objects.filter(pk=self.user.pk).delete()

        for row in (UserEvent.objects.get(event_type="view"), ExcelUpload.objects.get()):
            self.assertEqual(row.former_user_email, "user@example.com")
            self.assertEqual(row.former_user_name, "Ann Lee")
            self.assertIn("user@example.com", row.user_label(None))


class ExcelHelperTests(TestCase):
    def test_mode_is_case_insensitive(self):
        self.assertTrue(is_positive("Positive"))
        self.assertTrue(is_positive("positive"))
        self.assertFalse(is_positive("Negative"))
        self.assertFalse(is_positive(""))


HEADERS = [
    "Compound", "Parent compound", "Compound class", "Subclass", "Treatment", "Type",
    "Ionization mode", "Molecular formula [M]", "m/z ion", "References",
    "SMILE neutral formula", "Notes", "Fragment 1", "m/z fragment 1",
]


def import_rows(rows, **kwargs):
    from openpyxl import Workbook
    from .excel import import_excel

    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "data.xlsx"
        wb.save(path)
        return import_excel(str(path), skip_images=True, **kwargs)


def sheet_row(name, parent, type, cls="Pharma", sub="Antibiotic", smile="C", fragment=None):
    return [name, parent, cls, sub, "heat", type, "Positive", "C1", "100.1", "ref1", smile, "", *(fragment or [None, None])]


class ExcelImportTests(TestCase):
    def test_capitalised_original_type_links_tps_to_their_parent(self):
        import_rows([
            sheet_row("Drug", "Drug", "Original "),
            sheet_row("Drug TP1", "Drug", "TP"),
        ])
        drug = Compound.objects.get(name="Drug")
        self.assertEqual(drug.type, "original")
        self.assertIsNone(drug.origin)
        self.assertEqual(Compound.objects.get(name="Drug TP1").origin, drug)

    def test_same_tp_from_two_parents_is_kept_for_both(self):
        import_rows([
            sheet_row("A", "A", "Original"),
            sheet_row("B", "B", "Original"),
            sheet_row("Shared TP", "A", "TP"),
            sheet_row("Shared TP", "B", "TP"),
        ])
        self.assertEqual(Compound.objects.filter(name="Shared TP").count(), 2)

    def test_reimport_updates_instead_of_duplicating(self):
        import_rows([sheet_row("A", "A", "Original", smile="C")])
        import_rows([sheet_row("A", "A", "Original", smile="CC", fragment=["F", "5"])])
        compound = Compound.objects.get()
        self.assertEqual(compound.smile, "CC")
        self.assertEqual(compound.formulas.count(), 1)

    def test_same_subclass_name_under_two_classes(self):
        import_rows([
            sheet_row("A", "A", "Original", cls="One"),
            sheet_row("B", "B", "Original", cls="Two"),
        ])
        self.assertEqual(Subclass.objects.filter(name="Antibiotic").count(), 2)
        self.assertEqual(Compound.objects.get(name="B").subclass.clas.name, "Two")


class RegenerateCommandTests(TestCase):
    def test_invalid_compound_id_is_reported_not_raised(self):
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            call_command("regenerate_molecules", compound_id="nope", stdout=out)
        self.assertIn("Invalid compound ID", out.getvalue())


class FormulaCleanupTests(TestCase):
    def test_orphan_formulas_are_removed_but_shared_ones_stay(self):
        from .admin import CompoundAdmin
        from .models import FormulaMass
        from django.contrib import admin

        clas = Class.objects.create(name="C")
        sub = Subclass.objects.create(name="S", clas=clas)
        make = lambda n: Compound.objects.create(clas=clas, subclass=sub, type="TP", mode=True, name=n, neutral_formula="", mz_ion="", smile="")
        a, b = make("a"), make("b")
        shared = FormulaMass.objects.create(formula="x", mass="1")
        only_a = FormulaMass.objects.create(formula="y", mass="2")
        a.formulas.add(shared, only_a)
        b.formulas.add(shared)
        a.delete()
        CompoundAdmin(Compound, admin.site).remove_orphan_formulas()
        self.assertEqual(list(FormulaMass.objects.all()), [shared])
