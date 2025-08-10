import logging
from django.core.management.base import BaseCommand, CommandError
from core import excel

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process all pending Excel upload files by calling the import_excel command"

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-files",
            type=int,
            default=1,
            help="Maximum number of files to process in one run (default: 10)",
        )

    def handle(self, *args, **options):
        max_files = options["max_files"]
        try:
            excel.process_pending(max_files)
        except Exception as e:
            raise CommandError(f"Error importing data: {e}")
