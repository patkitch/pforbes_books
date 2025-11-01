# reports/views.py
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse

@staff_member_required
def health_check(request):
    return HttpResponse("Reports app is wired up.", content_type="text/plain")
