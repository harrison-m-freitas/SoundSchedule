from django.urls import path
from .views import generate_schedule, schedule_month, export_xlsx, export_ics

urlpatterns = [
    path("schedule/generate", generate_schedule, name="api_generate"),
    path("schedule/<int:year>/<int:month>", schedule_month, name="api_month"),
    path("export/xlsx", export_xlsx, name="api_export_xlsx"),
    path("export/ics", export_ics, name="api_export_ics"),
]
