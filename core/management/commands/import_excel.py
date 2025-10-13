import logging
from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook
from core.utils import ensure_media_directories, clear_data
from core import excel

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import data from Excel file into database models"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Path to Excel file to import")
        parser.add_argument(
            "--clear", action="store_true", help="Clear existing data before import"
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Skip molecule image generation (faster, avoids segfaults)",
        )

    def handle(self, *args, **options):
        file_path = options["file_path"]
        clear_data = options["clear"]
        skip_images = options.get("skip_images", False)

        try:
            wb = load_workbook(file_path, read_only=True)
            ws = wb.active
        except FileNotFoundError:
            raise CommandError(f'File "{file_path}" not found')
        except Exception as e:
            raise CommandError(f"Error reading Excel file: {e}")

        if clear_data:
            logger.warning(self.style.WARNING("Clearing all data"))
            excel.clear_data()

        if skip_images:
            logger.warning(self.style.WARNING("Skipping molecule image generation"))

        # Ensure media directories exist
        ensure_media_directories()

        try:
            imported_count = excel.import_excel_data(ws, skip_images)
            logger.info(
                self.style.SUCCESS(
                    f"Successfully imported {imported_count} total records"
                )
            )
        except Exception as e:
            raise CommandError(f"Error importing data: {e}")
