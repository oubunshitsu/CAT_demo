import csv
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


def _field_names(model):
    names = []
    for field in model._meta.fields:
        names.append(getattr(field, "attname", field.name))
    return names


def _extra_export_fields(model):
    extra = []
    if hasattr(model, "submitted_at_switzerland"):
        extra.append("submitted_at_switzerland")
    return extra


class Command(BaseCommand):
    help = "Export control-group app tables to CSV files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-dir",
            default="exports/ca_practice_control_group_gpt_freestyle",
            help="Output directory for CSV files.",
        )
        parser.add_argument(
            "--scope",
            choices=["app", "all"],
            default="app",
            help="app=control-group tables (+auth user), all=all managed models.",
        )

    def handle(self, *args, **options):
        out_dir = Path(options["out_dir"]).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        scope = options["scope"]
        all_models = apps.get_models(include_auto_created=True)
        tables = []
        user_model = get_user_model()
        if scope == "app":
            tables.append(user_model)
        for model in all_models:
            meta = model._meta
            if not meta.managed or meta.proxy or meta.swapped:
                continue
            if scope == "app" and meta.app_label != "ca_practice_control_group_gpt_freestyle":
                continue
            tables.append(model)

        tables.sort(key=lambda m: (m._meta.app_label, m._meta.model_name))

        for model in tables:
            filename = f"{model._meta.model_name}.csv"
            path = out_dir / filename
            fields = _field_names(model)
            extra_fields = _extra_export_fields(model)
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(fields + extra_fields)
                if extra_fields:
                    for obj in model.objects.all().iterator():
                        row = [getattr(obj, name) for name in fields]
                        for extra_name in extra_fields:
                            value = getattr(obj, extra_name)
                            row.append(value() if callable(value) else value)
                        writer.writerow(row)
                else:
                    for row in model.objects.all().values_list(*fields):
                        writer.writerow(row)

        self.stdout.write(
            self.style.SUCCESS(f"Exported {len(tables)} table(s) to {out_dir}")
        )
