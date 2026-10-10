"""Professional workflows on the existing native calendar."""
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from cookbook.helper.permission_helper import CustomIsGuest, CustomTokenHasReadWriteScope, has_group_permission
from cookbook.models import MealType
from cuaderno.api.base import CuadernoAPIView, CuadernoIsOperator
from cuaderno.models import CalendarEntry, MealCourse, MealPlanCourse, MenuTemplate, MenuTemplateEntry, SpaceProfile
from cuaderno.services.functional_access import Conflict, checked, lock_space, page_window, require_revision
from cuaderno.services.planning import (
    apply_template, course_payload, event_input, event_payload, plan_rows, print_document,
    replace_entries, require_professional, template_payload, visible_courses, visible_events,
    visible_plans, visible_templates,
)
from cuaderno.services.planning_inputs import DIETS, DECLARATION, STATUSES, date_range, fields, integer, template_input, text


class PlanningView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    def get(self, request):
        profile = require_professional(request.space)
        first, last = checked(date_range, request.query_params.get("from_date"), request.query_params.get("to_date"))
        diet, status = request.query_params.get("diet"), request.query_params.get("diet_status")
        if diet is not None and diet not in dict(DIETS):
            raise ValidationError({"diet": "Dieta desconocida."})
        if status is not None and (not diet or status not in STATUSES):
            raise ValidationError({"diet_status": "Elige una dieta y valoración válidas."})
        plans = list(visible_plans(request).filter(from_date__date__lte=last, to_date__date__gte=first)
                     .order_by("from_date", "meal_type__order", "cuaderno_course__course__position", "pk")[:1001])
        if len(plans) > 1000:
            raise ValidationError({"period": "Hay más de 1000 platos; reduce el periodo."})
        rows = plan_rows(request, plans, diet)
        if status:
            rows = [row for row in rows if row["diet_status"] == status]
        events = list(visible_events(request).filter(start_date__lte=last, end_date__gte=first)[:501])
        if len(events) > 500:
            raise ValidationError({"period": "Hay más de 500 anotaciones; reduce el periodo."})
        return Response({
            "courses": [course_payload(c) for c in visible_courses(request)], "meal_plans": rows,
            "events": [event_payload(e) for e in events], "can_edit": has_group_permission(request, ["user"]),
            "can_manage_absences": has_group_permission(request, ["admin"]),
            "can_merge_print": profile.edition == SpaceProfile.INTEGRAL, "declaration": DECLARATION,
        })


class CourseView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]
    http_method_names = ["post", "options"]

    def _data(self, request, course=None):
        checked(fields, request.data, ("name", "meal_type", "position", "revision"), ("name", "meal_type"))
        name = checked(text, request.data["name"])
        meal_type = get_object_or_404(MealType.objects.filter(space=request.space), pk=checked(integer, request.data["meal_type"]))
        position = checked(integer, request.data.get("position", 0), 0, 199)
        if visible_courses(request).filter(meal_type=meal_type, name=name).exclude(pk=course.pk if course else None).exists():
            raise Conflict("Ya existe un plato con ese nombre en esta comida.")
        return {"name": name, "meal_type": meal_type, "position": position}

    @transaction.atomic
    def post(self, request):
        lock_space(request); require_professional(request.space)
        if MealCourse.objects.filter(space=request.space).count() >= 200:
            raise ValidationError({"courses": "El espacio admite hasta 200 platos configurados."})
        row = MealCourse.objects.create(space=request.space, **self._data(request))
        return Response(course_payload(row), status=201)

    @transaction.atomic
    def put(self, request, course_id):
        lock_space(request); require_professional(request.space)
        row = get_object_or_404(visible_courses(request), pk=course_id)
        require_revision(request.data, course_payload(row)["revision"])
        data = self._data(request, row)
        if data["meal_type"].pk != row.meal_type_id and (
            MealPlanCourse.objects.filter(course=row).exists() or MenuTemplateEntry.objects.filter(course=row).exists()
        ):
            raise Conflict("Un plato usado en menús no puede trasladarse a otra comida.")
        for key, value in data.items():
            setattr(row, key, value)
        row.save()
        return Response(course_payload(row))

    @transaction.atomic
    def delete(self, request, course_id):
        lock_space(request); require_professional(request.space)
        row = get_object_or_404(visible_courses(request), pk=course_id)
        require_revision(request.query_params, course_payload(row)["revision"])
        try:
            row.delete()
        except ProtectedError as exc:
            raise Conflict("El plato se usa en menús o plantillas; retira esos vínculos antes de borrarlo.") from exc
        return Response(status=204)


class MealPlanCourseView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    @transaction.atomic
    def put(self, request, meal_plan_id):
        checked(fields, request.data, ("course",), ("course",))
        lock_space(request); require_professional(request.space)
        plan = get_object_or_404(visible_plans(request), pk=meal_plan_id)
        from cuaderno.services.service_plans import require_independent_meal_plan
        require_independent_meal_plan(plan)
        course_id = checked(integer, request.data["course"], nullable=True)
        course = None
        if course_id is not None:
            course = get_object_or_404(visible_courses(request), pk=course_id, meal_type_id=plan.meal_type_id)
        MealPlanCourse.objects.update_or_create(space=request.space, meal_plan=plan, defaults={"course": course})
        return Response(plan_rows(request, visible_plans(request).filter(pk=plan.pk))[0])


class MenuTemplateView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]
    http_method_names = ["get", "head", "post", "options"]

    def get(self, request, template_id=None):
        require_professional(request.space)
        rows = visible_templates(request)
        if template_id is not None:
            return Response(template_payload(get_object_or_404(rows, pk=template_id)))
        offset, limit = page_window(request, maximum=50)
        return Response({"count": rows.count(), "results": [template_payload(row) for row in rows[offset:offset + limit]]})

    @transaction.atomic
    def post(self, request):
        data = checked(template_input, request.data)
        lock_space(request); require_professional(request.space)
        row = MenuTemplate.objects.create(space=request.space, created_by=request.user, name=data["name"], weeks=data["weeks"])
        replace_entries(request, row, data["entries"])
        return Response(template_payload(get_object_or_404(visible_templates(request), pk=row.pk)), status=201)

    @transaction.atomic
    def put(self, request, template_id):
        data = checked(template_input, request.data)
        lock_space(request); require_professional(request.space)
        row = get_object_or_404(visible_templates(request), pk=template_id)
        require_revision(request.data, template_payload(row)["revision"])
        row.name, row.weeks = data["name"], data["weeks"]
        row.save()
        replace_entries(request, row, data["entries"])
        return Response(template_payload(get_object_or_404(visible_templates(request), pk=row.pk)))

    @transaction.atomic
    def delete(self, request, template_id):
        lock_space(request); require_professional(request.space)
        row = get_object_or_404(visible_templates(request), pk=template_id)
        require_revision(request.query_params, template_payload(row)["revision"])
        row.delete()
        return Response(status=204)


class MenuTemplateApplyView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    @transaction.atomic
    def post(self, request, template_id):
        lock_space(request); require_professional(request.space)
        row = get_object_or_404(visible_templates(request), pk=template_id)
        require_revision(request.data, template_payload(row)["revision"])
        return Response(apply_template(request, row, request.data), status=201)


class CalendarEntryView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request):
        lock_space(request); require_professional(request.space)
        row = CalendarEntry.objects.create(space=request.space, created_by=request.user, **event_input(request, request.data))
        return Response(event_payload(row), status=201)

    @transaction.atomic
    def put(self, request, entry_id):
        lock_space(request); require_professional(request.space)
        row = get_object_or_404(visible_events(request), pk=entry_id)
        require_revision(request.data, event_payload(row)["revision"])
        data = event_input(request, request.data)
        if data["kind"] != row.kind:
            raise ValidationError({"kind": "Conserva el tipo de la anotación; crea otra si cambia su finalidad."})
        for key, value in data.items():
            setattr(row, key, value)
        row.save()
        return Response(event_payload(row))

    @transaction.atomic
    def delete(self, request, entry_id):
        lock_space(request); require_professional(request.space)
        row = get_object_or_404(visible_events(request), pk=entry_id)
        require_revision(request.query_params, event_payload(row)["revision"])
        row.delete()
        return Response(status=204)


class MenuPrintView(CuadernoAPIView):
    # POST computes a read document; Consulta can print visible menus.
    permission_classes = [CustomIsGuest & CustomTokenHasReadWriteScope]

    def post(self, request):
        require_professional(request.space)
        return Response(print_document(request, request.data))


class CourseDetailView(CourseView):
    http_method_names = ["put", "delete", "options"]


class MenuTemplateDetailView(MenuTemplateView):
    http_method_names = ["get", "head", "put", "delete", "options"]


class CalendarEntryDetailView(CalendarEntryView):
    http_method_names = ["put", "delete", "options"]
