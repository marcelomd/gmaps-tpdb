import logging
import re
import uuid
from pathlib import Path
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Compound, Class, Subclass, Treatment
from .utils import add_user_event, client_ip

logger = logging.getLogger(__name__)

MOLECULE_FILENAME_RE = re.compile(r"molecule_[0-9a-f-]{36}(_[A-Za-z0-9]+)?\.png")

# (id param, id lookup, name param, name lookup, label); an id takes precedence over its name
COMPOUND_FILTERS = [
    ("class_id", "clas__id", "class_name", "clas__name__icontains", "class"),
    ("subclass_id", "subclass__id", "subclass_name", "subclass__name__icontains", "subclass"),
    ("origin_id", "origin__id", None, None, "origin"),
    ("treatment_id", "treatment__id", "treatment_name", "treatment__name__icontains", "treatment"),
]


def is_uuid(value):
    try:
        uuid.UUID(value)
    except (ValueError, TypeError):
        return False
    return True


def error_response(message, status):
    return JsonResponse({"status": "error", "message": message}, status=status)


def home_view(request):
    return render(request, "core/home.html")


@login_required
def query_view(request):
    add_user_event(request.user, 'view', {
        'page': 'query',
        'url': request.build_absolute_uri(),
        'ip': client_ip(request),
    })
    return render(request, "core/query.html")


@login_required
@require_http_methods(["GET"])
@cache_control(private=True, max_age=86400)
def molecule_image(request, filename):
    """Serve molecule images to logged-in users only; nothing else under MEDIA_ROOT is exposed"""
    # The strict pattern doubles as path-traversal protection
    if not MOLECULE_FILENAME_RE.fullmatch(filename):
        raise Http404
    path = Path(settings.MEDIA_ROOT) / "molecules" / filename
    if not path.is_file():
        raise Http404
    return FileResponse(path.open("rb"), content_type="image/png")


def serialize_compound(compound):
    molecule_image_url = None
    if compound.molecule_image and compound.molecule_image.name:
        try:
            molecule_image_url = compound.molecule_image.url
        except ValueError:
            # The field can hold a name with no file behind it
            pass

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
            {"id": str(compound.origin.id), "name": compound.origin.name}
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
        queryset = Compound.objects.select_related(
            "origin", "clas", "subclass"
        ).prefetch_related("treatment", "formulas")

        compound_id = request.GET.get("compound_id")
        if compound_id:
            if not is_uuid(compound_id):
                return error_response("Invalid compound ID format", 400)
            try:
                compound = queryset.get(id=compound_id)
            except Compound.DoesNotExist:
                return error_response("Compound not found", 404)
            result = serialize_compound(compound)
            # References are only included in the single-compound view
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

        filters = Q()
        for id_param, id_lookup, name_param, name_lookup, label in COMPOUND_FILTERS:
            id_value = request.GET.get(id_param)
            name_value = name_param and request.GET.get(name_param)
            if id_value:
                if not is_uuid(id_value):
                    return error_response(f"Invalid {label} ID format", 400)
                filters &= Q(**{id_lookup: id_value})
            elif name_value:
                filters &= Q(**{name_lookup: name_value})

        compound_type = request.GET.get("type")
        if compound_type:
            filters &= Q(type__iexact=compound_type)

        name = request.GET.get("name")
        if name:
            filters &= Q(name__icontains=name)

        if filters:
            # Filtering across the treatment M2M can repeat rows
            queryset = queryset.filter(filters).distinct()

        applied_filters = {
            key: value
            for key, value in request.GET.items()
            if key not in ["page", "page_size"] and value
        }
        add_user_event(request.user, 'query', {'filters': applied_filters})

        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = min(max(int(request.GET.get("page_size", 20)), 1), 100)
        except (ValueError, TypeError):
            page = 1
            page_size = 20

        paginator = Paginator(queryset, page_size)

        if page > paginator.num_pages and paginator.num_pages > 0:
            return error_response(
                f"Page {page} does not exist. Total pages: {paginator.num_pages}", 404
            )

        page_obj = paginator.get_page(page)

        response_data = {
            "status": "success",
            "data": [serialize_compound(compound) for compound in page_obj.object_list],
            "pagination": {
                "total": paginator.count,
                "page": page,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            },
        }
        if applied_filters:
            response_data["query"] = applied_filters

        return JsonResponse(response_data)

    except Exception:
        logger.exception("compounds_api failed")
        return error_response("Internal server error", 500)


@login_required
@require_http_methods(["GET"])
def metadata_api(request):
    """Reference data the query form needs to build its filters"""
    try:
        classes = Class.objects.all().order_by("name")
        subclasses = Subclass.objects.select_related("clas").all().order_by("name")
        treatments = Treatment.objects.all().order_by("name")

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

    except Exception:
        logger.exception("metadata_api failed")
        return JsonResponse(
            {"status": "error", "message": "Internal server error"}, status=500
        )
