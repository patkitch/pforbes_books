from django.contrib import admin
from .models import AgentRun, AgentEvent


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = (
        'agent_name',
        'run_type',
        'status',
        'started_at',
        'finished_at',
        'records_affected',
    )
    list_filter = (
        'agent_name',
        'run_type',
        'status',
        'started_at',
    )
    search_fields = (
        'agent_name',
    )
    date_hierarchy = 'started_at'
    ordering = ('-started_at',)


@admin.register(AgentEvent)
class AgentEventAdmin(admin.ModelAdmin):
    list_display = (
        'agent_run',
        'timestamp',
        'level',
        'short_message',
    )
    list_filter = (
        'level',
        'timestamp',
        'agent_run__agent_name',
    )
    search_fields = (
        'message',
        'agent_run__agent_name',
    )
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)

    def short_message(self, obj):
        # Show a shortened version of the event message in the list
        return (obj.message[:75] + '...') if len(obj.message) > 75 else obj.message

    short_message.short_description = 'Message'

