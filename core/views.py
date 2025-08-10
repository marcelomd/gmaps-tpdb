import json
import io
import base64
import logging
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Compound, Class, Subclass, Treatment

try:
    from rdkit import Chem
    from rdkit.Chem import Draw

    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

logger = logging.getLogger(__name__)


def home_view(request):
    logger.info("Home page accessed by user: %s", request.user)
    return render(request, "core/home.html")


@login_required
def query_view(request):
    """
    Query page for registered users to search compounds
    """
    return render(request, "core/query.html")


def serialize_compound(compound):
    """Custom serializer for Compound objects"""
    # Use stored molecule image if available
    molecule_image_url = None
    if compound.molecule_image and compound.molecule_image.name:
        try:
            molecule_image_url = compound.molecule_image.url
        except ValueError:
            # Handle case where image file doesn't exist
            molecule_image_url = None

    return {
        "id": str(compound.id),
        "name": compound.name,
        "type": compound.type,
        "mode": compound.mode,
        "neutral_formula": compound.neutral_formula,
        "mz_ion": compound.mz_ion,
        "smile": compound.smile,
        "molecule_image_url": molecule_image_url,
        "origin": (
            {
                "id": str(compound.origin.id) if compound.origin else None,
                "name": compound.origin.name if compound.origin else None,
            }
            if compound.origin
            else None
        ),
        "class": {"id": str(compound.clas.id), "name": compound.clas.name},
        "subclass": {"id": str(compound.subclass.id), "name": compound.subclass.name},
        "treatments": [
            {"id": str(treatment.id), "name": treatment.name}
            for treatment in compound.treatment.all()
        ],
        "formulas": [
            {"id": str(formula.id), "formula": formula.formula, "mass": formula.mass}
            for formula in compound.formulas.all()
        ],
    }


@login_required
@require_http_methods(["GET"])
def compounds_api(request):
    """
    Single endpoint to query compounds with various filters

    Query parameters:
    - class_id: Filter by class ID (UUID)
    - class_name: Filter by class name (case-insensitive contains)
    - subclass_id: Filter by subclass ID (UUID)
    - subclass_name: Filter by subclass name (case-insensitive contains)
    - type: Filter by compound type (exact match, e.g., 'TP')
    - origin_id: Filter compounds with specific origin compound (UUID)
    - treatment_id: Filter by treatment ID (UUID)
    - treatment_name: Filter by treatment name (case-insensitive contains)
    - compound_id: Get specific compound by ID (UUID)
    - name: Filter by compound name (case-insensitive contains)
    - page: Page number for pagination (default: 1)
    - page_size: Results per page (default: 20, max: 100)

    Example queries:
    - All compounds from class: ?class_id=123e4567-e89b-12d3-a456-426614174000
    - TP compounds from origin: ?type=TP&origin_id=123e4567-e89b-12d3-a456-426614174000
    - TP compounds with treatment: ?type=TP&treatment_name=heat
    - Combinations: ?class_name=alkaloids&type=TP&treatment_id=123e4567-e89b-12d3-a456-426614174000
    """
    try:
        # Start with all compounds, optimize with select_related and prefetch_related
        queryset = Compound.objects.select_related(
            "origin", "clas", "subclass"
        ).prefetch_related("treatment", "formulas")

        # Apply filters based on query parameters
        filters = Q()

        # Filter by specific compound ID
        compound_id = request.GET.get("compound_id")
        if compound_id:
            try:
                import uuid

                uuid.UUID(compound_id)
                compound = queryset.get(id=compound_id)
                result = serialize_compound(compound)
                # Add references for single compound view
                result["references"] = [
                    {"id": str(ref.id), "value": ref.value}
                    for ref in compound.references.all()
                ]
                return JsonResponse(
                    {
                        "status": "success",
                        "data": [result],
                        "pagination": {
                            "total": 1,
                            "page": 1,
                            "page_size": 1,
                            "total_pages": 1,
                        },
                    }
                )
            except Compound.DoesNotExist:
                return JsonResponse(
                    {"status": "error", "message": "Compound not found"}, status=404
                )
            except (ValueError, TypeError):
                return JsonResponse(
                    {"status": "error", "message": "Invalid compound ID format"},
                    status=400,
                )

        # Filter by class
        class_id = request.GET.get("class_id")
        class_name = request.GET.get("class_name")
        if class_id:
            # Validate UUID format
            try:
                import uuid

                uuid.UUID(class_id)
                filters &= Q(clas__id=class_id)
            except (ValueError, TypeError):
                return JsonResponse(
                    {"status": "error", "message": "Invalid class ID format"},
                    status=400,
                )
        elif class_name:
            filters &= Q(clas__name__icontains=class_name)

        # Filter by subclass
        subclass_id = request.GET.get("subclass_id")
        subclass_name = request.GET.get("subclass_name")
        if subclass_id:
            try:
                import uuid

                uuid.UUID(subclass_id)
                filters &= Q(subclass__id=subclass_id)
            except (ValueError, TypeError):
                return JsonResponse(
                    {"status": "error", "message": "Invalid subclass ID format"},
                    status=400,
                )
        elif subclass_name:
            filters &= Q(subclass__name__icontains=subclass_name)

        # Filter by compound type
        compound_type = request.GET.get("type")
        if compound_type:
            filters &= Q(type__iexact=compound_type)

        # Filter by origin compound
        origin_id = request.GET.get("origin_id")
        if origin_id:
            try:
                import uuid

                uuid.UUID(origin_id)
                filters &= Q(origin__id=origin_id)
            except (ValueError, TypeError):
                return JsonResponse(
                    {"status": "error", "message": "Invalid origin ID format"},
                    status=400,
                )

        # Filter by treatment
        treatment_id = request.GET.get("treatment_id")
        treatment_name = request.GET.get("treatment_name")
        if treatment_id:
            try:
                import uuid

                uuid.UUID(treatment_id)
                filters &= Q(treatment__id=treatment_id)
            except (ValueError, TypeError):
                return JsonResponse(
                    {"status": "error", "message": "Invalid treatment ID format"},
                    status=400,
                )
        elif treatment_name:
            filters &= Q(treatment__name__icontains=treatment_name)

        # Filter by compound name
        name = request.GET.get("name")
        if name:
            filters &= Q(name__icontains=name)

        # Apply all filters
        if filters:
            queryset = queryset.filter(filters).distinct()

        # Pagination
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = min(max(int(request.GET.get("page_size", 20)), 1), 100)
        except (ValueError, TypeError):
            page = 1
            page_size = 20

        paginator = Paginator(queryset, page_size)

        if page > paginator.num_pages and paginator.num_pages > 0:
            return JsonResponse(
                {
                    "status": "error",
                    "message": f"Page {page} does not exist. Total pages: {paginator.num_pages}",
                },
                status=404,
            )

        page_obj = paginator.get_page(page)

        # Serialize results
        results = [serialize_compound(compound) for compound in page_obj.object_list]

        # Build response
        response_data = {
            "status": "success",
            "data": results,
            "pagination": {
                "total": paginator.count,
                "page": page,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            },
        }

        # Add query info for transparency
        applied_filters = {}
        for key, value in request.GET.items():
            if key not in ["page", "page_size"] and value:
                applied_filters[key] = value

        if applied_filters:
            response_data["query"] = applied_filters

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": f"Internal server error: {str(e)}"},
            status=500,
        )


@login_required
@require_http_methods(["GET"])
def metadata_api(request):
    """
    Get metadata for building queries (classes, subclasses, treatments)
    """
    try:
        classes = Class.objects.all().order_by("name")
        subclasses = Subclass.objects.select_related("clas").all().order_by("name")
        treatments = Treatment.objects.all().order_by("name")

        # Get unique compound types
        compound_types = (
            Compound.objects.values_list("type", flat=True).distinct().order_by("type")
        )

        return JsonResponse(
            {
                "status": "success",
                "data": {
                    "classes": [
                        {"id": str(cls.id), "name": cls.name} for cls in classes
                    ],
                    "subclasses": [
                        {
                            "id": str(subcls.id),
                            "name": subcls.name,
                            "class_id": str(subcls.clas.id),
                            "class_name": subcls.clas.name,
                        }
                        for subcls in subclasses
                    ],
                    "treatments": [
                        {"id": str(treatment.id), "name": treatment.name}
                        for treatment in treatments
                    ],
                    "compound_types": list(compound_types),
                },
            }
        )

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
