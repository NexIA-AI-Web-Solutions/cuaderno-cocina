"""Extensions of native MealPlan: courses, reusable templates and safe printing."""
from datetime import datetime, time, timedelta

from django.db.models import F, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from cookbook.helper.permission_helper import get_household_user_ids, has_group_permission
from cookbook.models import MealPlan, MealType, ShoppingListRecipe
from cuaderno.models import (
    CalendarEntry, MealCourse, MealPlanCourse, MenuTemplate, MenuTemplateEntry,
    RecipeDietDeclaration, ServicePlan, SpaceProfile,
)
from cuaderno.services.costing import visible_recipes
from cuaderno.services.functional_access import Conflict, checked, revision
from cuaderno.services.planning_inputs import DIETS, DECLARATION, STATUSES, date_range, fields, integer, text


def require_professional(space, *, merged=False):
    from cuaderno.api.operations import _require
    return _require(space, SpaceProfile.INTEGRAL if merged else SpaceProfile.PROFESIONAL)


def visible_courses(request):
    return MealCourse.objects.filter(space=request.space, meal_type__space=request.space)


def course_payload(course):
    payload = {"id": course.pk, "name": course.name, "meal_type": course.meal_type_id, "position": course.position}
    return {**payload, "revision": revision(payload)}


def visible_plans(request):
    """Keep the native owner's/household's calendar; recipe access is additional."""
    recipes = visible_recipes(request.user, request.space)
    return MealPlan.objects.filter(space=request.space, meal_type__space=request.space).filter(
        Q(created_by=request.user) | Q(created_by_id__in=get_household_user_ids(request.user_space)),
    ).filter(Q(recipe_id__isnull=True) | Q(recipe_id__in=recipes.values("pk"))).filter(
        Q(cuaderno_course__isnull=True)
        | (Q(cuaderno_course__space=request.space)
           & (Q(cuaderno_course__course__isnull=True)
              | Q(cuaderno_course__course__space=request.space,
                  cuaderno_course__course__meal_type_id=F("meal_type_id")))
           & (Q(cuaderno_course__source_template__isnull=True)
              | Q(cuaderno_course__source_template__space=request.space))),
    ).select_related("recipe", "meal_type", "cuaderno_course__course")


def plan_rows(request, plans, diet=None):
    if diet is not None and (not isinstance(diet, str) or diet not in dict(DIETS)):
        raise ValidationError({"diet": "Dieta desconocida."})
    plans = list(plans)
    declarations = {}
    if diet:
        declarations = dict(RecipeDietDeclaration.objects.filter(
            space=request.space, recipe_id__in=[p.recipe_id for p in plans if p.recipe_id], slug=diet,
        ).values_list("recipe_id", "status"))
    result = []
    for plan in plans:
        extra = getattr(plan, "cuaderno_course", None)
        result.append({
            "id": plan.pk, "title": plan.title,
            "recipe": {"id": plan.recipe_id, "name": plan.recipe.name} if plan.recipe_id else None,
            "meal_type": {"id": plan.meal_type_id, "name": plan.meal_type.name},
            "course": extra.course_id if extra else None,
            "course_name": extra.course.name if extra and extra.course_id else None,
            "servings": format(plan.servings, "f"), "from_date": plan.from_date.isoformat(),
            "to_date": plan.to_date.isoformat(), "note": plan.note,
            "source_url": extra.source_url if extra else "",
            "diet_status": declarations.get(plan.recipe_id, "unknown"),
        })
    return result


def visible_templates(request):
    """Hide whole templates if any stored edge is incoherent or now private."""
    recipes = visible_recipes(request.user, request.space)
    invalid = MenuTemplateEntry.objects.filter(template__space=request.space).exclude(
        Q(space=request.space, meal_type__space=request.space, day_index__lt=F("template__weeks") * 7)
        & (Q(recipe__isnull=True) | Q(recipe_id__in=recipes.values("pk")))
        & (Q(course__isnull=True) | Q(course__space=request.space, course__meal_type_id=F("meal_type_id"))),
    )
    return MenuTemplate.objects.filter(space=request.space).exclude(pk__in=invalid.values("template_id")).prefetch_related(
        Prefetch("entries", queryset=MenuTemplateEntry.objects.select_related("recipe", "meal_type", "course")),
    ).order_by("name", "pk")


def template_payload(template):
    entries = [{
        "id": row.pk, "day_index": row.day_index, "meal_type": row.meal_type_id,
        "meal_type_name": row.meal_type.name, "course": row.course_id,
        "course_name": row.course.name if row.course_id else None,
        "recipe": row.recipe_id, "recipe_name": row.recipe.name if row.recipe_id else None,
        "title": row.title, "source_url": row.source_url, "servings": format(row.servings, "f"),
    } for row in template.entries.all()]
    value = {"id": template.pk, "name": template.name, "weeks": template.weeks, "entries": entries}
    from cuaderno.services.entity_media import image_payload
    image = image_payload("template", template)
    if image is not None:
        value["image"] = image
    value["revision"] = revision({**value, "updated_at": template.updated_at.isoformat()})
    return value


def validate_template_edges(request, entries):
    meal_types = {row.pk: row for row in MealType.objects.filter(
        space=request.space, pk__in={e["meal_type"] for e in entries},
    )}
    courses = {row.pk: row for row in visible_courses(request).filter(
        pk__in={e["course"] for e in entries if e["course"]},
    )}
    recipe_ids = {e["recipe"] for e in entries if e["recipe"]}
    if set(visible_recipes(request.user, request.space).filter(pk__in=recipe_ids).values_list("pk", flat=True)) != recipe_ids:
        raise NotFound("Alguna receta no está disponible.")
    for entry in entries:
        if entry["meal_type"] not in meal_types:
            raise NotFound("Alguna comida no está disponible.")
        if entry["course"] and (entry["course"] not in courses or courses[entry["course"]].meal_type_id != entry["meal_type"]):
            raise ValidationError({"course": "El plato debe pertenecer a la comida elegida."})
    return meal_types


def replace_entries(request, template, entries):
    validate_template_edges(request, entries)
    template.entries.all().delete()
    MenuTemplateEntry.objects.bulk_create([
        MenuTemplateEntry(space=request.space, template=template, day_index=e["day_index"],
                          meal_type_id=e["meal_type"], course_id=e["course"], recipe_id=e["recipe"],
                          title=e["title"], source_url=e["source_url"], servings=e["servings"])
        for e in entries
    ])


def apply_template(request, template, data):
    """Called inside the Space-locked transaction. Never overwrite arbitrary menus."""
    checked(fields, data, ("revision", "start_date", "overwrite"), ("revision", "start_date"))
    start, _ = checked(date_range, data["start_date"], data["start_date"])
    overwrite = data.get("overwrite", False)
    if type(overwrite) is not bool:
        raise ValidationError({"overwrite": "Confirma explícitamente si quieres reemplazar."})
    entries = list(template.entries.all())
    if not 1 <= len(entries) <= 200:
        raise ValidationError({"template": "La plantilla debe contener de 1 a 200 platos."})
    try:
        scheduled_days = [start + timedelta(days=entry.day_index) for entry in entries]
    except OverflowError as exc:
        raise ValidationError({"start_date": "La fecha de inicio deja platos fuera del calendario válido."}) from exc
    normalized = [{"meal_type": row.meal_type_id, "course": row.course_id, "recipe": row.recipe_id} for row in entries]
    meal_types = validate_template_edges(request, normalized)
    previous = MealPlanCourse.objects.filter(space=request.space, source_template=template,
                                             application_date=start, meal_plan__created_by=request.user)
    old_ids = list(previous.values_list("meal_plan_id", flat=True))
    # PostgreSQL FK inserts into shopping/service tables take KEY SHARE on
    # these rows. FOR UPDATE therefore serializes new references before the
    # dependency check and delete, even outside the extension's Space lock.
    list(MealPlan.objects.select_for_update().filter(
        space=request.space, created_by=request.user, pk__in=old_ids,
    ).values_list("pk", flat=True))
    # A private recipe change must not turn the overwrite path into a hidden delete.
    if set(visible_plans(request).filter(pk__in=old_ids).values_list("pk", flat=True)) != set(old_ids):
        raise NotFound("La aplicación previa no está disponible.")
    if old_ids and not overwrite:
        raise Conflict("Esta plantilla ya se aplicó en esa fecha. Confirma el reemplazo si procede.")
    if old_ids and (ShoppingListRecipe.objects.filter(mealplan_id__in=old_ids).exists()
                    or ServicePlan.objects.filter(meal_plan_id__in=old_ids).exists()):
        raise Conflict("El menú ya tiene compras o servicios vinculados; consérvalo y usa otra fecha.")
    # Only the requester's own slots are candidates; another household member's
    # independent menu is preserved, as are all unrelated native calendar rows.
    for entry, day in zip(entries, scheduled_days):
        existing = MealPlan.objects.filter(space=request.space, created_by=request.user,
                                          meal_type_id=entry.meal_type_id, from_date__date=day).exclude(pk__in=old_ids)
        if entry.course_id:
            existing = existing.filter(cuaderno_course__course_id=entry.course_id)
        else:
            existing = existing.filter(Q(cuaderno_course__isnull=True) | Q(cuaderno_course__course__isnull=True))
        if existing.exists():
            raise Conflict("Ya existe un menú en uno de esos días, comidas y platos. No se ha reemplazado.")
    if old_ids:
        MealPlan.objects.filter(space=request.space, created_by=request.user, pk__in=old_ids).delete()
    created = []
    for entry, day in zip(entries, scheduled_days):
        scheduled = timezone.make_aware(datetime.combine(day, meal_types[entry.meal_type_id].time or time(12)))
        plan = MealPlan.objects.create(space=request.space, created_by=request.user, recipe_id=entry.recipe_id,
                                       meal_type_id=entry.meal_type_id, title=entry.title, servings=entry.servings,
                                       from_date=scheduled, to_date=scheduled,
                                       note=("Referencia: " + entry.source_url) if entry.source_url else "")
        MealPlanCourse.objects.create(space=request.space, meal_plan=plan, course_id=entry.course_id,
                                      source_template=template, application_date=start, source_url=entry.source_url)
        created.append(plan.pk)
    return {"created_ids": created, "replaced_ids": old_ids}


def event_payload(row):
    payload = {"id": row.pk, "kind": row.kind, "title": row.title, "member_name": row.member_name,
               "start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat(), "note": row.note}
    return {**payload, "revision": revision({**payload, "updated_at": row.updated_at.isoformat()})}


def visible_events(request):
    rows = CalendarEntry.objects.filter(space=request.space)
    if not has_group_permission(request, ["admin"]):
        rows = rows.filter(kind="event")
    return rows


def event_input(request, data):
    checked(fields, data, ("kind", "title", "member_name", "start_date", "end_date", "note", "revision"),
            ("kind", "title", "start_date", "end_date"))
    kind = data["kind"]
    if kind not in ("event", "absence"):
        raise ValidationError({"kind": "Tipo de anotación desconocido."})
    if kind == "absence" and not has_group_permission(request, ["admin"]):
        raise PermissionDenied("Solo Responsable puede gestionar ausencias.")
    start, end = checked(date_range, data["start_date"], data["end_date"], maximum_days=366)
    member = checked(text, data.get("member_name", ""), empty=kind != "absence")
    if kind == "event" and member:
        raise ValidationError({"member_name": "Los datos personales de ausencias se guardan en una ausencia privada."})
    return {"kind": kind, "title": checked(text, data["title"]), "member_name": member,
            "start_date": start, "end_date": end, "note": checked(text, data.get("note", ""), 1000, empty=True)}


def print_document(request, data):
    checked(fields, data, ("orientation", "menus", "diet"), ("orientation", "menus"))
    if data["orientation"] not in ("portrait", "landscape"):
        raise ValidationError({"orientation": "Elige vertical u horizontal."})
    menus = data["menus"]
    if type(menus) is not list or not 1 <= len(menus) <= 5:
        raise ValidationError({"menus": "Selecciona entre uno y cinco menús."})
    require_professional(request.space, merged=len(menus) > 1)
    output = []
    for menu in menus:
        checked(fields, menu, ("name", "meal_plan_ids", "template_id"), ("name", "meal_plan_ids"))
        ids = menu["meal_plan_ids"]
        if type(ids) is not list or not 1 <= len(ids) <= 100:
            raise ValidationError({"meal_plan_ids": "Selecciona de 1 a 100 platos por menú."})
        ids = [checked(integer, pk) for pk in ids]
        if len(set(ids)) != len(ids):
            raise ValidationError({"meal_plan_ids": "No repitas platos dentro de un menú."})
        plans = list(visible_plans(request).filter(pk__in=ids).order_by("from_date", "meal_type__order", "cuaderno_course__course__position", "pk"))
        if len(plans) != len(ids):
            raise NotFound("Algún menú no está disponible.")
        item = {"name": checked(text, menu["name"]), "entries": plan_rows(request, plans, data.get("diet"))}
        if "template_id" in menu:
            template = get_object_or_404(visible_templates(request), pk=checked(integer, menu["template_id"]))
            from cuaderno.services.entity_media import image_payload
            item["image"] = image_payload("template", template)
        output.append(item)
    diet = data.get("diet")
    return {"orientation": data["orientation"], "merged": len(menus) > 1, "menus": output,
            "diet": diet, "diet_label": dict(DIETS).get(diet), "declaration": DECLARATION}
