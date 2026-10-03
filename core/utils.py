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

        compound.molecule_image.save(
            filename,
            ContentFile(buffer.getvalue()),
            save=False,  # The caller saves the compound
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
    molecules_dir = os.path.join(settings.MEDIA_ROOT, "molecules")

    os.makedirs(molecules_dir, exist_ok=True)


def clear_data():
    logger.info("Clearing existing data...")
    Compound.objects.all().delete()
    FormulaMass.objects.all().delete()
    Treatment.objects.all().delete()
    Reference.objects.all().delete()
    Subclass.objects.all().delete()
    Class.objects.all().delete()


def add_user_event(user, event_type, extra_data=None):
    """
    Create a user event record.

    Args:
        user: User instance
        event_type: str, one of the event type choices (e.g., 'login', 'view')
        extra_data: dict, optional additional data to store with the event

    Returns:
        UserEvent instance
    """
    from core.models import UserEvent

    return UserEvent.objects.create(
        user=user,
        event_type=event_type,
        extra_data=extra_data or {}
    )


def client_ip(request):
    """Caddy overwrites X-Real-IP; REMOTE_ADDR is empty behind the unix socket"""
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")
