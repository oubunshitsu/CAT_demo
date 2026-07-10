import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ca_practice.models import InitialArgument, IAPoint


class Command(BaseCommand):
    help = "Load IA points from ia_info-style JSON (points -> essential_ia_logic)."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_path",
            type=str,
            help="Path to ia_info JSON containing points.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing IAPoint rows before loading.",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json_path"])

        if not json_path.exists():
            raise CommandError(f"JSON file not found: {json_path}")

        if options["clear"]:
            self.stdout.write("Clearing existing IA points...")
            IAPoint.objects.all().delete()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Failed to parse JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise CommandError("JSON root must be an object mapping IA IDs to entries.")

        created = 0
        updated = 0
        for ia_id, entry in data.items():
            if not isinstance(entry, dict):
                continue
            points = entry.get("points") or {}
            if not isinstance(points, dict):
                continue
            ia = InitialArgument.objects.filter(initial_argument_id=ia_id).first()
            if not ia:
                self.stdout.write(f"Skipping IA {ia_id}: not found in InitialArgument")
                continue
            for point_id, point_entry in points.items():
                if not isinstance(point_entry, dict):
                    continue
                point_text = (point_entry.get("essential_ia_logic") or "").strip()
                if not point_text:
                    continue
                obj, was_created = IAPoint.objects.update_or_create(
                    initial_argument=ia,
                    ia_point_id=str(point_id),
                    defaults={"point_text": point_text},
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished loading IA points (created={created}, updated={updated})."
            )
        )
