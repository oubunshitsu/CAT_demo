import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ca_practice.models import Topic, InitialArgument


class Command(BaseCommand):
    help = "Load Topic and InitialArgument data from a JSON file (ia_info-style)."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_path",
            type=str,
            help="Path to JSON file containing topic/IA entries.",
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing Topic and InitialArgument rows before loading.",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json_path"])

        if not json_path.exists():
            raise CommandError(f"JSON file not found: {json_path}")

        if options["clear"]:
            self.stdout.write("Clearing existing InitialArgument and Topic data...")
            InitialArgument.objects.all().delete()
            Topic.objects.all().delete()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Failed to parse JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise CommandError("JSON root must be an object mapping IDs to entries.")

        count = 0
        for key, value in data.items():
            if not isinstance(value, dict):
                self.stdout.write(f"Skipping non-object entry at key {key!r}")
                continue

            topic_text = (
                value.get("topic_text")
                or value.get("topic")
                or value.get("topic_name")
                or value.get("title")
                or key
            )
            ia_text = (
                value.get("initial_argument_text")
                or value.get("essay")
                or value.get("text")
            )

            if not ia_text:
                self.stdout.write(f"Skipping key {key!r}: missing initial argument text")
                continue

            topic_id_raw = value.get("topic_id")
            topic_id = None
            try:
                topic_id = int(topic_id_raw) if topic_id_raw is not None else None
            except (TypeError, ValueError):
                topic_id = None
            if topic_id is not None:
                topic, _ = Topic.objects.update_or_create(
                    topic_id=topic_id, defaults={"topic_text": topic_text}
                )
            else:
                topic, _ = Topic.objects.get_or_create(topic_text=topic_text)

            ia_id = str(value.get("initial_argument_id") or "").strip()
            if not ia_id:
                raise CommandError(
                    f"Entry {key!r} missing 'initial_argument_id' (string required)."
                )

            stance = (value.get("stance") or "pro").strip().lower()
            if stance not in {"pro", "con"}:
                stance = "pro"
            ia, created = InitialArgument.objects.update_or_create(
                initial_argument_id=ia_id,
                defaults={
                    "topic": topic,
                    "stance": stance,
                    "initial_argument_text": ia_text.strip(),
                },
            )

            count += 1
            self.stdout.write(
                f"{'Created' if created else 'Updated'} IA "
                f"{ia.initial_argument_id} for Topic {topic.topic_id}"
            )

        self.stdout.write(
            self.style.SUCCESS(f"Finished loading Topics and InitialArguments ({count} rows).")
        )
