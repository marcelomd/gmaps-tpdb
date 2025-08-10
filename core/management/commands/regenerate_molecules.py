from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Compound
from core.utils import generate_and_save_molecule_image, ensure_media_directories


class Command(BaseCommand):
    help = "Regenerate molecule images for all compounds with SMILE data"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', 
            action='store_true', 
            help='Force regeneration even if image already exists'
        )
        parser.add_argument(
            '--compound-id', 
            type=str, 
            help='Regenerate image for specific compound ID'
        )
        parser.add_argument(
            '--missing-only', 
            action='store_true', 
            help='Only generate images for compounds that don\'t have them'
        )

    def handle(self, *args, **options):
        ensure_media_directories()
        
        force = options['force']
        compound_id = options['compound_id']
        missing_only = options['missing_only']
        
        # Filter compounds
        queryset = Compound.objects.filter(smile__isnull=False).exclude(smile='')
        
        if compound_id:
            try:
                queryset = queryset.filter(id=compound_id)
                if not queryset.exists():
                    self.stdout.write(
                        self.style.ERROR(f'Compound with ID {compound_id} not found or has no SMILE data')
                    )
                    return
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f'Invalid compound ID format: {compound_id}')
                )
                return
        
        if missing_only and not force:
            queryset = queryset.filter(molecule_image='')
        
        total_compounds = queryset.count()
        
        if total_compounds == 0:
            self.stdout.write(
                self.style.WARNING('No compounds found matching the specified criteria.')
            )
            return
        
        self.stdout.write(f'Processing {total_compounds} compounds...')
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        with transaction.atomic():
            for compound in queryset:
                # Skip if image exists and not forcing
                if compound.molecule_image and not force and not missing_only:
                    skipped_count += 1
                    continue
                
                try:
                    if generate_and_save_molecule_image(compound, force_regenerate=force):
                        compound.save()
                        success_count += 1
                        self.stdout.write(f'✓ Generated image for: {compound.name}')
                    else:
                        error_count += 1
                        self.stdout.write(f'✗ Failed to generate image for: {compound.name}')
                        
                except Exception as e:
                    error_count += 1
                    self.stdout.write(f'✗ Error processing {compound.name}: {e}')
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(f'SUMMARY:')
        self.stdout.write(f'  Successfully generated: {success_count}')
        self.stdout.write(f'  Errors: {error_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Total processed: {success_count + error_count + skipped_count}')
        
        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'\nSuccessfully generated {success_count} molecule images!')
            )
        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(f'Encountered {error_count} errors during processing.')
            )