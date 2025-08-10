from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook
from core.models import Class, Subclass, Treatment, Reference, Compound, FormulaMass
from core.utils import generate_and_save_molecule_image, ensure_media_directories


class Command(BaseCommand):
    help = "Import data from Excel file into database models"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Path to Excel file to import")
        parser.add_argument(
            "--clear", action="store_true", help="Clear existing data before import"
        )

    def field(self, row, col):
        return row[col].strip().lower() if row[col] else ""
    
    def create_formula_mass_models(self, row, col_nums):
        """Create FormulaMass models for F1-F10 columns and return list of created objects"""
        formula_mass_objects = []
        
        # Handle F1-F10 pairs
        for i in range(1, 11):
            formula_col_name = f"formula f{i} [m+h]"
            mz_col_name = f"m/z f{i}"
            
            # Special case for F2 which has different naming
            if i == 2:
                formula_col_name = "ion formula f2"
            
            formula_col = col_nums.get(formula_col_name)
            mz_col = col_nums.get(mz_col_name)
            
            if formula_col is not None and mz_col is not None:
                formula_value = row[formula_col] if row[formula_col] else ""
                mz_value = row[mz_col] if row[mz_col] else ""
                
                # Only create if both formula and m/z have values
                if formula_value.strip() and mz_value:
                    formula_mass_obj, created = FormulaMass.objects.get_or_create(
                        formula=formula_value.strip(),
                        mass=str(mz_value).strip()
                    )
                    formula_mass_objects.append(formula_mass_obj)
                    if created:
                        self.stdout.write(f"Created FormulaMass: {formula_mass_obj.formula} - {formula_mass_obj.mass}")
        
        return formula_mass_objects

    def handle(self, *args, **options):
        file_path = options["file_path"]
        clear_data = options["clear"]

        try:
            wb = load_workbook(file_path, read_only=True)
            ws = wb.active
        except FileNotFoundError:
            raise CommandError(f'File "{file_path}" not found')
        except Exception as e:
            raise CommandError(f"Error reading Excel file: {e}")

        if clear_data:
            self.stdout.write(self.style.WARNING("Clearing existing data..."))
            Compound.objects.all().delete()
            FormulaMass.objects.all().delete()
            Treatment.objects.all().delete()
            Reference.objects.all().delete()
            Subclass.objects.all().delete()
            Class.objects.all().delete()

        # Ensure media directories exist
        ensure_media_directories()

        try:
            with transaction.atomic():
                imported_count = self.import_excel_data(ws)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully imported {imported_count} total records"
                    )
                )
        except Exception as e:
            raise CommandError(f"Error importing data: {e}")

    def import_excel_data(self, ws):
        # Get column headers
        for r in ws.iter_rows(min_row=1, max_row=1, values_only=True):
            all_cols = r

        col_nums = {}
        for i, n in enumerate(all_cols):
            if n is None:
                continue
            col_nums[n.strip().lower()] = i

        self.stdout.write(f"Found columns: {list(col_nums.keys())}")

        # Map column names
        name_col = col_nums.get("composto")
        origin_col = col_nums.get("composto de origem")
        class_col = col_nums.get("classe")
        subclass_col = col_nums.get("subclasse")
        treatment_col = col_nums.get("tratamento")
        type_col = col_nums.get("tipo de composto")
        mode_col = col_nums.get("modo")
        neutral_col = col_nums.get("formula neutra [m]")
        mz_col = col_nums.get("m/z íon")
        reference_col = col_nums.get("reference")
        smile_col = col_nums.get("smile (fórmula neutra)")

        if None in [
            name_col,
            class_col,
            subclass_col,
            type_col,
            mode_col,
            neutral_col,
            mz_col,
            smile_col,
        ]:
            raise CommandError("Missing required columns in Excel file")

        classes = {}
        subclasses = {}
        treatments = {"-": None, "": None}
        references = {"-": None, "": None}
        originals = {}
        tps = {}
        total_count = 0

        # Process all rows
        for r in ws.iter_rows(min_row=2, values_only=True):
            if r[0] is None:
                continue

            c = self.field(r, class_col)
            if c and c not in classes:
                obj, created = Class.objects.get_or_create(name=c)
                classes[c] = obj
                if created:
                    self.stdout.write(f"Created Class: {obj}")
                    total_count += 1

            s = self.field(r, subclass_col)
            if s and s not in subclasses:
                obj, created = Subclass.objects.get_or_create(name=s, clas=classes[c])
                subclasses[s] = obj
                if created:
                    self.stdout.write(f"Created Subclass: {obj}")
                    total_count += 1

            t = self.field(r, treatment_col)
            if t:
                # Split treatments by semicolon and create individual treatments
                treatment_names = [
                    name.strip().lower() for name in t.split(";") if name.strip()
                ]
                for treatment_name in treatment_names:
                    if treatment_name not in treatments:
                        obj, created = Treatment.objects.get_or_create(
                            name=treatment_name
                        )
                        treatments[treatment_name] = obj
                        if created:
                            self.stdout.write(f"Created Treatment: {obj}")
                            total_count += 1

            # Handle references (semicolon-separated list)
            ref = self.field(r, reference_col)
            if ref:
                # Split references by semicolon and create individual references
                reference_values = [
                    v.strip().lower() for v in ref.split(";") if v.strip()
                ]
                for reference_value in reference_values:
                    if reference_value not in references:
                        obj, created = Reference.objects.get_or_create(
                            value=reference_value
                        )
                        references[reference_value] = obj
                        if created:
                            self.stdout.write(f"Created Reference: {obj}")
                            total_count += 1

            origin = self.field(r, origin_col)
            name = self.field(r, name_col)

            if self.field(r, type_col) == "original":
                originals[origin] = r
            else:
                tps[name] = r

        # Create original compounds
        for origin, r in originals.items():
            obj, created = Compound.objects.get_or_create(
                origin=None,
                clas=classes[self.field(r, class_col)],
                subclass=subclasses[self.field(r, subclass_col)],
                type="original",
                mode=True if self.field(r, mode_col) == "positivo" else False,
                name=self.field(r, name_col),
                neutral_formula=r[neutral_col] or "",
                mz_ion=str(r[mz_col]) if r[mz_col] else "",
                smile=r[smile_col] or "",
            )

            # Handle treatments (semicolon-separated list)
            treatment_field = self.field(r, treatment_col)
            if treatment_field:
                treatment_names = [
                    t.strip().lower() for t in treatment_field.split(";") if t.strip()
                ]
                for treatment_name in treatment_names:
                    if treatment_name in treatments and treatments[treatment_name]:
                        obj.treatment.add(treatments[treatment_name])

            # Handle references (semicolon-separated list)
            if reference_col is not None:
                ref_field = self.field(r, reference_col)
                if ref_field:
                    reference_values = [
                        v.strip().lower() for v in ref_field.split(";") if v.strip()
                    ]
                    for ref_value in reference_values:
                        if ref_value in references and references[ref_value]:
                            obj.references.add(references[ref_value])

            # Handle FormulaMass models (F1-F10 columns)
            formula_mass_objects = self.create_formula_mass_models(r, col_nums)
            for formula_mass_obj in formula_mass_objects:
                obj.formulas.add(formula_mass_obj)
            if formula_mass_objects:
                total_count += len(formula_mass_objects)

            # Generate and save molecule image
            if obj.smile:
                if generate_and_save_molecule_image(obj):
                    obj.save()  # Save the compound with the image
                    self.stdout.write(f"Generated molecule image for: {obj.name}")

            originals[origin] = obj
            if created:
                self.stdout.write(f"Created Original Compound: {obj}")
                total_count += 1

        # Create TP compounds
        for name, r in tps.items():
            origin_name = self.field(r, origin_col)
            origin_compound = originals.get(origin_name)

            obj, created = Compound.objects.get_or_create(
                origin=origin_compound,
                clas=classes[self.field(r, class_col)],
                subclass=subclasses[self.field(r, subclass_col)],
                type="TP",
                mode=True if self.field(r, mode_col) == "positivo" else False,
                name=name,
                neutral_formula=r[neutral_col] or "",
                mz_ion=str(r[mz_col]) if r[mz_col] else "",
                smile=r[smile_col] or "",
            )

            # Handle treatments (semicolon-separated list)
            treatment_field = self.field(r, treatment_col)
            if treatment_field:
                treatment_names = [
                    t.strip().lower() for t in treatment_field.split(";") if t.strip()
                ]
                for treatment_name in treatment_names:
                    if treatment_name in treatments and treatments[treatment_name]:
                        obj.treatment.add(treatments[treatment_name])

            # Handle references (semicolon-separated list)
            if reference_col is not None:
                ref_field = self.field(r, reference_col)
                if ref_field:
                    reference_values = [
                        v.strip().lower() for v in ref_field.split(";") if v.strip()
                    ]
                    for ref_value in reference_values:
                        if ref_value in references and references[ref_value]:
                            obj.references.add(references[ref_value])

            # Handle FormulaMass models (F1-F10 columns)
            formula_mass_objects = self.create_formula_mass_models(r, col_nums)
            for formula_mass_obj in formula_mass_objects:
                obj.formulas.add(formula_mass_obj)
            if formula_mass_objects:
                total_count += len(formula_mass_objects)

            # Generate and save molecule image
            if obj.smile:
                if generate_and_save_molecule_image(obj):
                    obj.save()  # Save the compound with the image
                    self.stdout.write(f"Generated molecule image for: {obj.name}")

            if created:
                self.stdout.write(f"Created TP Compound: {obj}")
                total_count += 1

        return total_count
