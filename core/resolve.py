from dataclasses import dataclass, field

from core.models import (
    Class,
    ClassAlias,
    Subclass,
    SubclassAlias,
    Treatment,
    TreatmentAlias,
)
from core.normalize import clean, norm_key, similar_keys


@dataclass
class ImportReport:
    """What an import added to the controlled vocabularies, for a human to review"""

    created: dict = field(default_factory=dict)  # kind -> [display name]
    similar: list = field(default_factory=list)  # new names close to an existing one

    def to_dict(self):
        return {"created": self.created, "similar": self.similar}

    def summary_lines(self):
        lines = []
        for kind, names in self.created.items():
            lines.append(f"{len(names)} new {kind}: {', '.join(names)}")
        for item in self.similar:
            lines.append(
                f"{item['kind']} \"{item['name']}\" looks like "
                + ", ".join(f'"{n}"' for n in item["similar_to"])
            )
        return lines


class Vocabulary:
    """Entries of one kind, found by key or alias; unknown names are created once

    An existing entry is never renamed: the first spelling stored is the one that stays.
    """

    def __init__(self, kind, model, alias_model, report, scope=None):
        self.kind = kind
        self.model = model
        self.report = report
        self.scope = scope or {}
        self.display = {}  # key or alias key -> display name
        self.by_key = {}
        for obj in model.objects.filter(**self.scope):
            self.by_key[obj.key] = obj
            self.display[obj.key] = obj.name
        for alias in alias_model.objects.filter(
            **{f"target__{k}": v for k, v in self.scope.items()}
        ).select_related("target"):
            self.by_key[alias.key] = alias.target
            self.display[alias.key] = alias.target.name

    def resolve(self, name):
        key = norm_key(name)
        obj = self.by_key.get(key)
        if obj:
            return obj
        similar = similar_keys(key, self.display)
        obj = self.model.objects.create(name=clean(name), **self.scope_values())
        self.by_key[key] = obj
        self.display[key] = obj.name
        self.report.created.setdefault(self.kind, []).append(obj.name)
        if similar:
            names = list(dict.fromkeys(self.display[k] for k in similar))
            self.report.similar.append(
                {"kind": self.kind, "name": obj.name, "similar_to": names}
            )
        return obj

    def scope_values(self):
        return self.scope


class Vocabularies:
    """Class, subclass and treatment lookups for one import"""

    def __init__(self, report):
        self.report = report
        self.classes = Vocabulary("class", Class, ClassAlias, report)
        self.treatments = Vocabulary("treatment", Treatment, TreatmentAlias, report)
        self._subclasses = {}

    def clas(self, name):
        return self.classes.resolve(name)

    def subclass(self, clas, name):
        # Subclass names are only unique within their class
        vocab = self._subclasses.get(clas.pk)
        if vocab is None:
            vocab = Vocabulary(
                "subclass", Subclass, SubclassAlias, self.report, scope={"clas": clas}
            )
            self._subclasses[clas.pk] = vocab
        return vocab.resolve(name)

    def treatment(self, name):
        return self.treatments.resolve(name)
