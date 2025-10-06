from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf.urls.static import static
from django.templatetags.static import static as static_url

from scheduling import urls as scheduling_urls
from scheduling.api.v1.urls import urlpatterns as api_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include(scheduling_urls)),
    path("api/v1/", include((api_urls, "api"))),

    path("favicon.ico", RedirectView.as_view(
        url=static_url("favicon/favicon.ico"),
        permanent=True
    )),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
