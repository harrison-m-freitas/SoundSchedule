from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import HttpResponse
import tempfile, os

from scheduling.services.exporters.export_xlsx import export_schedule_xlsx
from scheduling.services.exporters.export_ics import export_schedule_ics
from scheduling.services.suggestion import suggest_for_month
from scheduling.services.calendar import ensure_month_services

from scheduling.domain.models import Service
from scheduling.domain.repositories import ServiceRepository
from scheduling.utils import _get_ym_from_request

from .serializers import ServiceSerializer

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_schedule(request):
    year, month, err = _get_ym_from_request(request)
    if err:
        return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)
    services_created = ensure_month_services(year, month)
    created, count = suggest_for_month(year, month, user=request.user)
    return Response(
        {"created": bool(created), "assignments": count, "services_created": services_created},
        status=status.HTTP_201_CREATED if created or services_created else status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def schedule_month(request, year: int, month: int):
    if not (1 <= month <= 12):
        return Response({"detail": "Mês inválido"}, status=status.HTTP_400_BAD_REQUEST)
    services = list(ServiceRepository.month_services(year, month))
    total = len(services)
    limit_raw = request.query_params.get("limit")
    offset_raw = request.query_params.get("offset", 0)
    try:
        limit = int(limit_raw) if limit_raw is not None else total
        offset = int(offset_raw) if offset_raw is not None else 0
        if limit is not None and limit < 0: raise ValueError
        if offset < 0: raise ValueError
    except Exception:
        return Response({"detail": "Parâmetros 'limit' e 'offset' devem ser inteiros >= 0."}, status=status.HTTP_400_BAD_REQUEST)
    if limit is not None:
        qs = services[offset:offset+limit]
    elif offset:
        qs = services[offset:]
    data = ServiceSerializer(qs, many=True).data
    if limit is not None or offset:
        return Response({"count": total, "limit": limit, "offset": offset, "results": data})
    return Response(data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_xlsx(request):
    year, month, err = _get_ym_from_request(request)
    if err:
        return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, f"escala-{year}-{month:02d}.xlsx")
        export_schedule_xlsx(year, month, path)
        with open(path, "rb") as f:
            content = f.read()
    resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="escala-{year}-{month:02d}.xlsx"'
    return resp

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_ics(request):
    year, month, err = _get_ym_from_request(request)
    if err:
        return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)
    content = export_schedule_ics(year, month)
    resp = HttpResponse(content, content_type="text/calendar")
    resp["Content-Disposition"] = f'attachment; filename="escala-{year}-{month:02d}.ics"'
    return resp
