from django.core.management.base import BaseCommand, CommandError

from core.merge import merge_entries
from core.models import (
    Class,
    ClassAlias,
    Subclass,
    SubclassAlias,
    Treatment,
    TreatmentAlias,
)
from core.normalize import norm_key


class Command(BaseCommand):
    help = (
        "Merge entries that mean the same thing (synonyms, typos) into one. The merged "
        "names are remembered as aliases so later uploads using them land on the kept entry."
    )

    def add_arguments(self, parser):
        parser.add_argument("kind", choices=["class", "subclass", "treatment"])
        parser.add_argument("keep", help="Name of the entry that stays")
        parser.add_argument("merge", nargs="+", help="Names to merge into it")
        parser.add_argument(
            "--class", dest="class_name", help="Class the subclasses belong to"
        )

    def find(self, model, alias_model, name, **scope):
        key = norm_key(name)
        obj = model.objects.filter(key=key, **scope).first()
        if obj is None:
            alias = alias_model.objects.filter(
                key=key, **{f"target__{k}": v for k, v in scope.items()}
            ).first()
            obj = alias.target if alias else None
        if obj is None:
            raise CommandError(f'No {model._meta.verbose_name} named "{name}"')
        return obj

    def handle(self, *args, **options):
        kind = options["kind"]
        scope = {}
        if kind == "subclass":
            if not options["class_name"]:
                raise CommandError("--class is required for subclasses")
            scope = {"clas": self.find(Class, ClassAlias, options["class_name"])}
        model, alias_model = {
            "class": (Class, ClassAlias),
            "subclass": (Subclass, SubclassAlias),
            "treatment": (Treatment, TreatmentAlias),
        }[kind]

        keep = self.find(model, alias_model, options["keep"], **scope)
        dups = [self.find(model, alias_model, n, **scope) for n in options["merge"]]
        merged = merge_entries(kind, keep, dups)
        self.stdout.write(self.style.SUCCESS(f'Merged {merged} into "{keep.name}"'))
