import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ca_practice.models import (
    ChatHistory,
    CounterArgument,
    IdentifiedCAStructure,
    NoStructureChatHistory,
)


class Command(BaseCommand):
    help = "Export selected ca_practice tables to CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default=".",
            help="Directory to write CSV files (default: current directory).",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).resolve()
        if not output_dir.exists():
            raise CommandError(f"Output directory does not exist: {output_dir}")

        exports = [
            ("CounterArgument.csv", CounterArgument, ["counter_argument_id", "user_id", "initial_argument_id", "counter_argument_text"]),
            ("IdentifiedCAStructure.csv", IdentifiedCAStructure, ["identified_id", "user_id", "counter_argument_id", "template_structure_id", "z"]),
            ("ChatHistory.csv", ChatHistory, ["chat_history_id", "user_id", "counter_argument_id", "template_structure_id", "template_cq_id", "history_text_dict"]),
            ("NoStructureChatHistory.csv", NoStructureChatHistory, ["chat_history_id", "counter_argument_id", "history_text_dict"]),
        ]

        for filename, model, fields in exports:
            filepath = output_dir / filename
            queryset = model.objects.all().values_list(*fields)
            self.stdout.write(f"Writing {filepath} ...")
            with filepath.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(fields)
                for row in queryset:
                    writer.writerow(row)

        self.stdout.write(self.style.SUCCESS("CSV export complete."))
