import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ca_practice.models import Topic, InitialArgument, IAPoint


class Command(BaseCommand):
    help = "Load Topic and InitialArgument data from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            type=str,
            help="Path to CSV file containing topics and initial arguments.",
        )
        parser.add_argument(
            "--points-csv",
            type=str,
            default="",
            help="Optional CSV file containing IA points.",
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
                # x/y are now derived from IA points; ignore CSV x/y columns if present.
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

        points_csv = options["points_csv"]
        if points_csv:
            from ca_practice.models import IAPoint

            points_path = Path(points_csv)
            if not points_path.exists():
                raise CommandError(f"Points CSV file not found: {points_path}")

            with points_path.open(encoding="utf-8") as pf:
                points_reader = csv.DictReader(pf)
                for row in points_reader:
                    ia_id = (row.get("initial_argument_id") or "").strip()
                    point_id = (row.get("ia_point_id") or "").strip()
                    point_text = (row.get("point_text") or "").strip()
                    if not ia_id or not point_id or not point_text:
                        continue
                    ia = InitialArgument.objects.filter(initial_argument_id=ia_id).first()
                    if not ia:
                        continue
                    IAPoint.objects.update_or_create(
                        initial_argument=ia,
                        ia_point_id=point_id,
                        defaults={"point_text": point_text},
                    )

        self.stdout.write(
            self.style.SUCCESS("Finished loading Topics and InitialArguments.")
        )
