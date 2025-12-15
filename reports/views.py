# reports/views.py
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.http import FileResponse, Http404
from pathlib import Path

def download_report(request, filename):
    # This points to the folder where *this file* lives (the reports app folder)
    reports_app_dir = Path(__file__).resolve().parent

    file_path = reports_app_dir / filename

    if not file_path.exists() or not file_path.is_file():
        raise Http404("Report not found")

    return FileResponse(open(file_path, "rb"), as_attachment=True, filename=filename)


@staff_member_required
def health_check(request):
    return HttpResponse("Reports app is wired up.", content_type="text/plain")
