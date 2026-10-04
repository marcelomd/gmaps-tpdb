import tempfile
import uuid
from pathlib import Path
from unittest import mock

from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from .excel import is_positive
from .models import (
    Class, ClassAlias, Compound, ExcelUpload, Subclass, Treatment, TreatmentAlias, UserEvent,
)
from .resolve import ImportReport


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


class NormalizeTests(TestCase):
    def test_key_ignores_case_and_whitespace_but_keeps_acronyms_apart_from_words(self):
        from .normalize import norm_key

        self.assertEqual(norm_key("Photo-Fenton"), norm_key(" photo-fenton"))
        self.assertEqual(norm_key("Electron\xa0beam  irradiation"), norm_key("electron beam irradiation"))
        self.assertNotEqual(norm_key("MPUV"), norm_key("MPUV/PMS"))

    def test_treatments_split_on_semicolon_and_comma_space_and_dedupe_by_case(self):
        from .normalize import split_treatments

        self.assertEqual(
            split_treatments("Photolysis ; Photo-Fenton, Electro-Fenton;electro-fenton;;"),
            ["Photolysis", "Photo-Fenton", "Electro-Fenton"],
        )
        self.assertEqual(split_treatments("1,2-dichloroethane"), ["1,2-dichloroethane"])


class CaseInsensitiveImportTests(TestCase):
    def treatment_names(self):
        return sorted(Treatment.objects.values_list("name", flat=True))

    def test_spellings_in_one_file_become_one_entry_with_the_first_spelling(self):
        report = ImportReport()
        import_rows([
            sheet_row("A", "A", "Original", cls="Pharma", sub="Antibiotic"),
            sheet_row("B", "B", "original", cls="pharma", sub="ANTIBIOTIC"),
        ], report=report)
        self.assertEqual(Class.objects.count(), 1)
        self.assertEqual(Subclass.objects.count(), 1)
        self.assertEqual(Class.objects.get().name, "Pharma")
        self.assertEqual(Subclass.objects.get().name, "Antibiotic")
        self.assertEqual(Compound.objects.filter(clas=Class.objects.get()).count(), 2)

    def test_acronyms_are_stored_as_written_and_never_renamed_by_later_uploads(self):
        def row(name, treatment):
            r = sheet_row(name, name, "Original")
            r[4] = treatment
            return r

        import_rows([row("A", "MPUV/PMS; Photo-Fenton")])
        import_rows([row("B", "mpuv/pms; photo-fenton; Solar AOP")])
        self.assertEqual(self.treatment_names(), ["MPUV/PMS", "Photo-Fenton", "Solar AOP"])
        self.assertEqual(Compound.objects.get(name="B").treatment.count(), 2 + 1)

    def test_sheet_column_variants_do_not_break_treatment_links(self):
        def row(name, treatment):
            r = sheet_row(name, name, "Original")
            r[4] = treatment
            return r

        import_rows([row("A", "Electron\xa0beam irradiation; electro-Fenton, Electro-Fenton")])
        self.assertEqual(self.treatment_names(), ["Electron beam irradiation", "electro-Fenton"])

    def test_alias_sends_a_known_synonym_to_the_kept_entry(self):
        kept = Treatment.objects.create(name="Ozonation")
        TreatmentAlias.objects.create(key="Ozonization", target=kept)

        def row(treatment):
            r = sheet_row("A", "A", "Original")
            r[4] = treatment
            return r

        import_rows([row("OZONIZATION")])
        self.assertEqual(self.treatment_names(), ["Ozonation"])
        self.assertEqual(Compound.objects.get().treatment.get(), kept)

    def test_report_lists_new_names_and_flags_lookalikes(self):
        Treatment.objects.create(name="Ozonation")
        report = ImportReport()

        def row(treatment):
            r = sheet_row("A", "A", "Original")
            r[4] = treatment
            return r

        import_rows([row("Ozonization; Ozonation")], report=report)
        self.assertEqual(report.created["treatment"], ["Ozonization"])
        self.assertEqual(
            report.similar,
            [{"kind": "treatment", "name": "Ozonization", "similar_to": ["Ozonation"]}],
        )

    def test_unknown_type_or_mode_rejects_the_upload_and_names_the_rows(self):
        bad_type = sheet_row("A", "A", "Metabolite")
        bad_mode = sheet_row("B", "B", "Original")
        bad_mode[6] = "Positve"
        with self.assertRaises(Exception) as ctx:
            import_rows([bad_type, bad_mode])
        self.assertIn('unknown type "Metabolite" (rows 2)', str(ctx.exception))
        self.assertIn('unknown ionization mode "Positve" (rows 3)', str(ctx.exception))
        self.assertEqual(Compound.objects.count(), 0)

    def test_mode_and_type_accept_any_case(self):
        r = sheet_row("A", "A", "ORIGINAL")
        r[6] = " negative "
        import_rows([r])
        self.assertFalse(Compound.objects.get().mode)


class ModelKeyTests(TestCase):
    def test_database_refuses_a_case_duplicate(self):
        from django.db import IntegrityError, transaction

        Treatment.objects.create(name="Photo-Fenton")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Treatment.objects.create(name="photo-fenton")

    def test_admin_validation_reports_a_case_duplicate(self):
        from django.core.exceptions import ValidationError

        Treatment.objects.create(name="Photo-Fenton")
        with self.assertRaises(ValidationError):
            Treatment(name="PHOTO-FENTON").full_clean()

    def test_alias_cannot_shadow_an_existing_entry(self):
        from django.core.exceptions import ValidationError

        kept = Treatment.objects.create(name="Ozonation")
        Treatment.objects.create(name="Ozone oxidation")
        with self.assertRaises(ValidationError):
            TreatmentAlias(key="ozone OXIDATION", target=kept).full_clean()


class MergeTests(TestCase):
    def make(self, clas, sub, name, treatments=()):
        c = Compound.objects.create(
            clas=clas, subclass=sub, type="TP", mode=True, name=name,
            neutral_formula="", mz_ion="", smile="",
        )
        c.treatment.set(treatments)
        return c

    def test_treatment_merge_moves_compounds_once_and_records_alias(self):
        from .merge import merge_entries

        clas = Class.objects.create(name="C")
        sub = Subclass.objects.create(name="S", clas=clas)
        keep = Treatment.objects.create(name="Ozonation")
        dup = Treatment.objects.create(name="Ozonization")
        both = self.make(clas, sub, "both", [keep, dup])
        only_dup = self.make(clas, sub, "only", [dup])
        merge_entries("treatment", keep, [dup])
        self.assertEqual(list(both.treatment.all()), [keep])
        self.assertEqual(list(only_dup.treatment.all()), [keep])
        self.assertFalse(Treatment.objects.filter(name="Ozonization").exists())
        self.assertEqual(TreatmentAlias.objects.get().target, keep)

    def test_class_merge_combines_subclasses_with_the_same_name(self):
        from .merge import merge_entries

        keep = Class.objects.create(name="Pharma")
        dup = Class.objects.create(name="Pharmaceuticals")
        keep_sub = Subclass.objects.create(name="Antibiotic", clas=keep)
        dup_same = Subclass.objects.create(name="antibiotic", clas=dup)
        dup_other = Subclass.objects.create(name="Steroid", clas=dup)
        a = self.make(dup, dup_same, "a")
        b = self.make(dup, dup_other, "b")
        merge_entries("class", keep, [dup])
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.clas, a.subclass), (keep, keep_sub))
        self.assertEqual((b.clas, b.subclass.clas), (keep, keep))
        self.assertEqual(Class.objects.count(), 1)
        self.assertEqual(Subclass.objects.count(), 2)
        self.assertEqual(ClassAlias.objects.get().key, "pharmaceuticals")

    def test_subclasses_of_different_classes_cannot_merge(self):
        from .merge import merge_entries

        one = Subclass.objects.create(name="S", clas=Class.objects.create(name="One"))
        two = Subclass.objects.create(name="S", clas=Class.objects.create(name="Two"))
        with self.assertRaises(ValueError):
            merge_entries("subclass", one, [two])

    def test_command_merges_by_name_and_alias(self):
        from django.core.management import call_command

        Treatment.objects.create(name="Ozonation")
        Treatment.objects.create(name="Ozonization")
        call_command("merge_names", "treatment", "ozonation", "OZONIZATION", stdout=mock.MagicMock())
        self.assertEqual(list(Treatment.objects.values_list("name", flat=True)), ["Ozonation"])


class AdminMergeTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser("root@example.com", password="x")
        self.client.force_login(self.admin)
        self.a = Treatment.objects.create(name="Ozonation")
        self.b = Treatment.objects.create(name="Ozonization")
        self.url = reverse("admin:core_treatment_changelist")

    def post(self, **extra):
        return self.client.post(self.url, {
            "action": "merge_selected",
            "_selected_action": [str(self.a.pk), str(self.b.pk)],
            **extra,
        })

    def test_action_asks_which_entry_to_keep_then_merges(self):
        response = self.post()
        self.assertContains(response, "Ozonization")
        self.assertEqual(Treatment.objects.count(), 2)
        self.post(confirm_merge="1", keep=str(self.a.pk))
        self.assertEqual(list(Treatment.objects.all()), [self.a])

    def test_change_pages_render(self):
        self.assertEqual(self.client.get(reverse("admin:core_treatment_change", args=[self.a.pk])).status_code, 200)
        upload = ExcelUpload.objects.create(file="x.xlsx", report={"created": {"treatment": ["T"]}, "similar": []})
        response = self.client.get(reverse("admin:core_excelupload_change", args=[upload.pk]))
        self.assertContains(response, "1 new treatment: T")


class DuplicateMigrationTests(TransactionTestCase):
    def test_existing_case_duplicates_are_merged_when_migrating(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0008_keys_and_aliases")])
        apps = executor.loader.project_state([("core", "0008_keys_and_aliases")]).apps
        H = {n: apps.get_model("core", n) for n in ("Class", "Subclass", "Treatment", "Compound")}
        clas = H["Class"].objects.create(name="Pharma")
        sub = H["Subclass"].objects.create(name="Antibiotic", clas=clas)
        big = H["Treatment"].objects.create(name="Solar Photo-Fenton")
        small = H["Treatment"].objects.create(name="Solar photo-Fenton")
        make = lambda n, t: H["Compound"].objects.create(
            clas=clas, subclass=sub, type="TP", mode=True, name=n,
            neutral_formula="", mz_ion="", smile="",
        ).treatment.add(*t)
        make("a", [big]); make("b", [big]); make("c", [small])

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

        self.assertEqual(list(Treatment.objects.values_list("name", flat=True)), ["Solar Photo-Fenton"])
        self.assertEqual(Compound.objects.filter(treatment__name="Solar Photo-Fenton").count(), 3)
