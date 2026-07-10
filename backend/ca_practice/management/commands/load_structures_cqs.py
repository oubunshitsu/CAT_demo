import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ca_practice.models import TemplateCAStructure, TemplateCQ


class Command(BaseCommand):
    help = "Load TemplateCAStructure and TemplateCQ from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_path",
            type=str,
            help="Path to JSON file containing structures and their CQs.",
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing TemplateCAStructure and TemplateCQ rows before loading.",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json_path"])

        if not json_path.exists():
            raise CommandError(f"JSON file not found: {json_path}")

        if options["clear"]:
            self.stdout.write(
                "Clearing existing TemplateCQ and TemplateCAStructure data..."
            )
            TemplateCQ.objects.all().delete()
            TemplateCAStructure.objects.all().delete()

        with json_path.open(encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f"Error parsing JSON: {e}")

        if not isinstance(data, list):
            raise CommandError("Top-level JSON must be a list of structures.")

        for struct_obj in data:
            name = (struct_obj.get("name") or "").strip()
            text = (struct_obj.get("text") or "").strip()
            cqs = struct_obj.get("cqs") or []

            if not name:
                raise CommandError("Each structure must have a non-empty 'name'.")
            if not text:
                raise CommandError(
                    f"Structure '{name}' must have a non-empty 'text' field."
                )
            if not isinstance(cqs, list):
                raise CommandError(f"'cqs' for structure '{name}' must be a list.")

            # Upsert structure by name
            struct, created = TemplateCAStructure.objects.update_or_create(
                template_structure_name=name,
                defaults={"template_structure_text": text},
            )

            # Clear existing CQs for this structure, then add from JSON
            struct.template_cqs.all().delete()

            for cq_text in cqs:
                cq_text_clean = (cq_text or "").strip()
                if not cq_text_clean:
                    continue
                TemplateCQ.objects.create(
                    template_structure=struct,
                    template_cq_text=cq_text_clean,
                )

            self.stdout.write(
                f"{'Created' if created else 'Updated'} structure "
                f"{struct.template_structure_id} ('{struct.template_structure_name}') "
                f"with {len(cqs)} CQs."
            )

        self.stdout.write(self.style.SUCCESS("Finished loading structures and CQs."))

