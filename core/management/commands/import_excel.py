import logging
from django.core.management.base import BaseCommand, CommandError
from core.utils import ensure_media_directories
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
        if options["clear"]:
            logger.warning(self.style.WARNING("Clearing all data"))
        if options["skip_images"]:
            logger.warning(self.style.WARNING("Skipping molecule image generation"))

        ensure_media_directories()

        try:
            imported_count = excel.import_excel(
                options["file_path"], options["clear"], options["skip_images"]
            )
        except Exception as e:
            raise CommandError(f"Error importing data: {e}")
        logger.info(
            self.style.SUCCESS(f"Successfully imported {imported_count} total records")
        )
