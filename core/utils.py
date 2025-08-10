import os
import io
import logging
from django.core.files.base import ContentFile
from django.conf import settings
from core.models import Class, Subclass, Treatment, Reference, Compound, FormulaMass


logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import Draw

    RDKIT_AVAILABLE = True
except ImportError as e:
    logger.error(f"Error importing rdkit {e}", exc_info=True)
    RDKIT_AVAILABLE = False


def generate_and_save_molecule_image(compound, size=(300, 200), force_regenerate=False):
    """
    Generate and save a molecule image from a compound's SMILE string.

    Args:
        compound: Compound model instance
        size: tuple of (width, height) for the image
        force_regenerate: bool, whether to regenerate even if image exists

    Returns:
        bool: True if image was generated successfully, False otherwise
    """
    logger.info(
        f"Starting image generation for compound: {compound.name}, SMILE: {compound.smile[:50] if compound.smile else 'None'}"
    )

    if not RDKIT_AVAILABLE:
        logger.warning(f"RDKit not available")
        return False

    if not compound.smile:
        logger.warning(f"No SMILE string for compound {compound.name}")
        return False

    # Skip if image already exists and not forcing regeneration
    if compound.molecule_image and not force_regenerate:
        logger.info(f"Image already exists for {compound.name}, skipping")
        return True

    try:
        mol = Chem.MolFromSmiles(compound.smile)
        if mol is None:
            logger.warning(
                f"Failed to parse SMILE for compound {compound.name}: {compound.smile}"
            )
            return False

        img = Draw.MolToImage(mol, size=size)
        logger.info(f"Image generated for {compound.name}")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        logger.info(f"Image saved to buffer for {compound.name}")

        filename = f"molecule_{compound.id}.png"

        # Save to the molecule_image field
        compound.molecule_image.save(
            filename,
            ContentFile(buffer.getvalue()),
            save=False,  # Don't save the model yet, let the caller do it
        )
        return True

    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        logger.error(
            f"Error generating molecule image for compound {compound.name}: {e}",
            exc_info=True,
        )
        return False


def ensure_media_directories():
    """Ensure that media directories exist"""
    media_root = settings.MEDIA_ROOT
    molecules_dir = os.path.join(media_root, "molecules")

    os.makedirs(molecules_dir, exist_ok=True)
    print(f"Ensured media directory exists: {molecules_dir}")


def get_molecule_image_url(compound):
    """Get the URL for a compound's molecule image"""
    if compound.molecule_image and compound.molecule_image.name:
        return compound.molecule_image.url
    return None


def cleanup_orphaned_molecule_images():
    """Clean up molecule image files that no longer have corresponding compounds"""
    from .models import Compound

    if not settings.MEDIA_ROOT:
        return

    molecules_dir = os.path.join(settings.MEDIA_ROOT, "molecules")
    if not os.path.exists(molecules_dir):
        return

    # Get all existing compound IDs
    compound_ids = set(str(compound.id) for compound in Compound.objects.all())

    # Check all files in molecules directory
    for filename in os.listdir(molecules_dir):
        if filename.startswith("molecule_") and filename.endswith(".png"):
            # Extract compound ID from filename
            compound_id = filename.replace("molecule_", "").replace(".png", "")

            if compound_id not in compound_ids:
                file_path = os.path.join(molecules_dir, filename)
                try:
                    os.remove(file_path)
                    print(f"Removed orphaned molecule image: {filename}")
                except OSError as e:
                    print(f"Error removing orphaned file {filename}: {e}")


def clear_data():
    logger.info("Clearing existing data...")
    Compound.objects.all().delete()
    FormulaMass.objects.all().delete()
    Treatment.objects.all().delete()
    Reference.objects.all().delete()
    Subclass.objects.all().delete()
    Class.objects.all().delete()
