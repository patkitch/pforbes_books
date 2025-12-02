from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.pauly.core import upload_image_to_wordpress


class Command(BaseCommand):
    help = (
        "Pauly: Test uploading a single image file to the WordPress media library. "
        "This does not create a product; it only uploads the image."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--image-path",
            type=str,
            required=True,
            help="Full path to the local image file to upload.",
        )
        parser.add_argument(
            "--title",
            type=str,
            default=None,
            help="Optional title for the media item.",
        )
        parser.add_argument(
            "--alt-text",
            type=str,
            default=None,
            help="Optional alt text for the media item.",
        )

    def handle(self, *args, **options):
        image_path = options["image_path"]
        title = options.get("title")
        alt_text = options.get("alt_text")

        # 1. Start AgentRun
        run = AgentRun.objects.create(
            agent_name="Pauly",
            run_type="manual",
            started_at=timezone.now(),
            status="running",
        )

        def log(level, message, extra=None):
            AgentEvent.objects.create(
                agent_run=run,
                timestamp=timezone.now(),
                level=level,
                message=message,
                extra=extra or {},
            )
            self.stdout.write(f"[{level.upper()}] {message}")

        try:
            log(
                "info",
                f"Pauly starting image upload test for: {image_path}",
            )

            media = upload_image_to_wordpress(
                image_path=image_path,
                title=title,
                alt_text=alt_text,
            )

            media_id = media.get("id")
            source_url = media.get("source_url")

            log(
                "info",
                f"Image uploaded successfully. Media ID={media_id}, URL={source_url}",
                extra={"media": media},
            )

            run.status = "success"
            run.records_affected = 1
            run.finished_at = timezone.now()
            run.save()

        except FileNotFoundError as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()
            log("error", f"File not found: {str(e)}")
            raise CommandError(str(e))

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()
            log("error", f"Pauly image upload test failed: {str(e)}")
            raise e
