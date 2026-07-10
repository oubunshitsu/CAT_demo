import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ca_practice_control_group_gpt_freestyle.models import Topic, InitialArgument


class Command(BaseCommand):
    help = "Load Topic and InitialArgument data from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            type=str,
            help="Path to CSV file containing topics and initial arguments.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing Topic and InitialArgument rows before loading.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])

        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        if options["clear"]:
            self.stdout.write("Clearing existing InitialArgument and Topic data...")
            InitialArgument.objects.all().delete()
            Topic.objects.all().delete()

        def build_ia_id(topic_id_value: str, topic_text_value: str, stance: str) -> str:
            if topic_id_value:
                base = topic_id_value
            else:
                base = re.sub(r"[^A-Za-z0-9]+", "_", topic_text_value.upper()).strip("_")
                if not base:
                    raise CommandError(
                        "Cannot build initial_argument_id without topic_id or a valid topic_text."
                    )
            return f"{base}_{stance}"

        with csv_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # --- Topic ---
                topic_id_raw = (row.get("topic_id") or "").strip()
                topic_text = (row.get("topic_text") or "").strip()

                if not topic_text:
                    raise CommandError("Each row must have a non-empty 'topic_text'.")

                if topic_id_raw:
                    topic_id = int(topic_id_raw)
                    topic, _ = Topic.objects.update_or_create(
                        topic_id=topic_id,
                        defaults={"topic_text": topic_text},
                    )
                else:
                    topic, _ = Topic.objects.get_or_create(topic_text=topic_text)

                # --- InitialArgument ---
                ia_text_pro = (row.get("initial_argument_text_pro") or "").strip()
                ia_text_con = (row.get("initial_argument_text_con") or "").strip()

                if not ia_text_pro or not ia_text_con:
                    raise CommandError(
                        "Each row must have non-empty 'initial_argument_text_pro' "
                        "and 'initial_argument_text_con'."
                    )

                stance_payloads = (
                    ("pro", ia_text_pro),
                    ("con", ia_text_con),
                )
                created = False
                for stance, ia_text in stance_payloads:
                    ia_id = build_ia_id(topic_id_raw, topic_text, stance.upper())
                    ia, created = InitialArgument.objects.update_or_create(
                        initial_argument_id=ia_id,
                        defaults={
                            "topic": topic,
                            "stance": stance,
                            "initial_argument_text": ia_text,
                        },
                    )

                self.stdout.write(
                    f"{'Created' if created else 'Updated'} IA {ia.initial_argument_id} "
                    f"for Topic {topic.topic_id}"
                )

        self.stdout.write(
            self.style.SUCCESS("Finished loading Topics and InitialArguments.")
        )
