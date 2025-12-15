"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from reports.views_inventory_safe import SafeInventoryRecountView
from django.http import FileResponse
from pathlib import Path

def download_report(request, filename):
    path = Path("reports") / filename
    return FileResponse(open(path, "rb"), as_attachment=True)

urlpatterns = [
    path("", RedirectView.as_view(url="/ledger/", permanent=False)),  # <— add this line
    path('admin/', admin.site.urls),
    path('ledger/', include(("django_ledger.urls","django_ledger"),namespace="django_ledger")),
    path("ledger/inventory-recount/<slug:entity_slug>/",
        SafeInventoryRecountView.as_view(),
        name="safe-inventory-recount"),
    path("admin/reports/", include(("reports.urls_admin", "adminreports"), namespace="adminreports")),
    path("automation/", include("web_automation.urls")),
    path("forbes-lawn/", include("forbes_lawn_dashboard.urls")),
    path("downloads/<str:filename>/", download_report),
]
