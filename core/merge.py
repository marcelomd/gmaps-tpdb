"""Merging entries (class, subclass, treatment) that stand for the same thing

Every function takes `m`, a namespace of model classes (Class, Subclass, Treatment,
Compound and the three *Alias models). Pass `core.models` normally, or a namespace
built from `apps.get_model` inside a migration so historical models are used.
"""

from collections import defaultdict

from core.normalize import norm_key


def _has_inner_capitals(name):
    return any(c.isupper() for c in name[1:])


def _survivor(rows, usage):
    """The entry that keeps existing: most used, then the spelling that has inner capitals
    (acronyms, proper names), then alphabetical so the choice is deterministic"""
    return min(rows, key=lambda r: (-usage(r), not _has_inner_capitals(r.name), r.name))


def _add_alias(Alias, keep, dup_key, **extra):
    if dup_key != keep.key:
        Alias.objects.get_or_create(key=dup_key, defaults={"target": keep, **extra}, **extra)


def merge_treatments(m, keep, dup):
    dup_key = norm_key(dup.name)
    through = m.Compound.treatment.through
    already = through.objects.filter(treatment=keep).values("compound_id")
    through.objects.filter(treatment=dup).exclude(compound_id__in=already).update(
        treatment_id=keep.pk
    )
    m.TreatmentAlias.objects.filter(target=dup).update(target=keep)
    _add_alias(m.TreatmentAlias, keep, dup_key)
    dup.delete()


def merge_subclasses(m, keep, dup):
    dup_key = norm_key(dup.name)
    m.Compound.objects.filter(subclass=dup).update(subclass=keep)
    m.SubclassAlias.objects.filter(target=dup).update(target=keep)
    _add_alias(m.SubclassAlias, keep, dup_key, clas_id=keep.clas_id)
    dup.delete()


def merge_classes(m, keep, dup):
    dup_key = norm_key(dup.name)
    keep_subs = {s.key: s for s in m.Subclass.objects.filter(clas=keep)}
    for sub in m.Subclass.objects.filter(clas=dup):
        twin = keep_subs.get(sub.key)
        if twin:
            merge_subclasses(m, twin, sub)
        else:
            sub.clas = keep
            sub.save()
            m.SubclassAlias.objects.filter(target=sub).update(clas=keep)
    m.Compound.objects.filter(clas=dup).update(clas=keep)
    m.ClassAlias.objects.filter(target=dup).update(target=keep)
    _add_alias(m.ClassAlias, keep, dup_key)
    dup.delete()


def dedupe_all(m):
    """Give every existing row its key and merge those that differ only in case/whitespace"""
    for model in (m.Class, m.Subclass, m.Treatment):
        for row in model.objects.all():
            row.key = norm_key(row.name)
            row.save()

    # Classes first: merging them can bring subclasses together
    groups = defaultdict(list)
    for clas in m.Class.objects.all():
        groups[clas.key].append(clas)
    for rows in groups.values():
        if len(rows) > 1:
            keep = _survivor(rows, lambda r: m.Compound.objects.filter(clas=r).count())
            for dup in rows:
                if dup.pk != keep.pk:
                    merge_classes(m, keep, dup)

    groups = defaultdict(list)
    for sub in m.Subclass.objects.all():
        groups[(sub.clas_id, sub.key)].append(sub)
    for rows in groups.values():
        if len(rows) > 1:
            keep = _survivor(rows, lambda r: m.Compound.objects.filter(subclass=r).count())
            for dup in rows:
                if dup.pk != keep.pk:
                    merge_subclasses(m, keep, dup)

    groups = defaultdict(list)
    for treatment in m.Treatment.objects.all():
        groups[treatment.key].append(treatment)
    for rows in groups.values():
        if len(rows) > 1:
            keep = _survivor(
                rows, lambda r: m.Compound.objects.filter(treatment=r).count()
            )
            for dup in rows:
                if dup.pk != keep.pk:
                    merge_treatments(m, keep, dup)


def merge_entries(kind, keep, dups):
    """Merge `dups` into `keep` (same kind, subclasses within one class); aliases keep old spellings working"""
    from django.db import transaction

    from core import models as real

    merge = {
        "class": merge_classes,
        "subclass": merge_subclasses,
        "treatment": merge_treatments,
    }[kind]
    dups = [d for d in dups if d.pk != keep.pk]
    if kind == "subclass" and any(d.clas_id != keep.clas_id for d in dups):
        raise ValueError("Subclasses can only be merged within the same class")
    with transaction.atomic():
        for dup in dups:
            merge(real, keep, dup)
    return len(dups)
