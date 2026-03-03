from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.welcome.urls")),
    path("dashboard/", include("apps.company.urls")),
    path("catalog/", include("apps.catalog.urls", namespace="catalog")),
    path("purchasing/", include("apps.purchasing.urls", namespace="purchasing")),
    path("stock/", include("apps.stock.urls")),
    path("production/", include("apps.production.urls")),
    path("planning/", include("apps.planning.urls")),
    path("sales/", include("apps.sales.urls")),
    path("pms/", include("apps.pms.urls")),
    path("pricing/", include("apps.pricing.urls", namespace="pricing")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)