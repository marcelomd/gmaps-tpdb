import logging
import os
import re
from io import StringIO
import sys
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction
from core.models import ExcelUpload

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process all pending Excel upload files by calling the import_excel command"

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-files',
            type=int,
            default=10,
            help='Maximum number of files to process in one run (default: 10)'
        )

    def handle(self, *args, **options):
        max_files = options['max_files']

        # Get pending uploads ordered by upload time
        pending_uploads = ExcelUpload.objects.filter(status='pending').order_by('uploaded_at')[:max_files]

        if not pending_uploads:
            self.stdout.write("No pending Excel uploads found.")
            return

        self.stdout.write(f"Found {len(pending_uploads)} pending upload(s) to process.")

        processed_count = 0
        failed_count = 0

        for upload in pending_uploads:
            self.stdout.write(f"Processing: {upload.file.name}")

            try:
                self.process_upload(upload)
                processed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Successfully processed: {upload.file.name}")
                )
            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f"✗ Failed to process: {upload.file.name} - {str(e)}")
                )
                logger.error(f"Failed to process upload {upload.id}: {str(e)}", exc_info=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Processing complete. Processed: {processed_count}, Failed: {failed_count}"
            )
        )

    def process_upload(self, upload):
        """Process a single ExcelUpload"""
        # Check if file exists
        if not upload.file or not os.path.exists(upload.file.path):
            upload.status = 'error'
            upload.error_message = "File not found"
            upload.save()
            raise Exception("File not found")

        # Update status to processing
        upload.status = 'processing'
        upload.save()

        file_path = upload.file.path

        # Capture stdout to get import statistics
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            with transaction.atomic():
                # Call import_excel command with or without --clear flag
                if upload.clear_existing_data:
                    call_command('import_excel', file_path, '--clear')
                else:
                    call_command('import_excel', file_path)

                output = captured_output.getvalue()

                # Extract number of imported records
                imported_matches = re.findall(r'Successfully imported (\d+) total records', output)
                if imported_matches:
                    upload.records_imported = int(imported_matches[0])

                # Mark as completed
                upload.status = 'completed'
                upload.error_message = None  # Clear any previous error
                upload.save()

        except Exception as e:
            upload.status = 'error'
            upload.error_message = str(e)
            upload.save()
            raise e
        finally:
            sys.stdout = old_stdout