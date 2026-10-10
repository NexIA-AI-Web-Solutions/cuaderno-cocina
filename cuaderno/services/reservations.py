"""Customer reservations reuse native menus, service snapshots and stock ledger."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, localcontext
import hashlib
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from cookbook.helper.permission_helper import has_group_permission
from cookbook.models import MealPlan
from cuaderno.models import CustomerReservation, ReservationRevision, ReservationService, ServicePlan
from cuaderno.services.costing import visible_recipes
from cuaderno.services.functional_access import Conflict, lock_space
from cuaderno.services.planning import require_professional, visible_templates
from cuaderno.services.service_plans import confirm_service_plan, cancel_service_plan, produce_service_plan, reverse_service_plan, serialize_service_plan

MENU_FIELDS = {'template', 'template_day', 'meal_type'}
BASIC_FIELDS = {'customer_name', 'phone', 'email', 'service_date', 'service_time', 'covers', 'note'}


def can_manage(request):
    return has_group_permission(request, ['admin'])


def can_operate(request, row=None):
    household = getattr(getattr(request, 'user_space', None), 'household', None)
    if household is None or household.space_id != request.space.pk:
        return False
    if not has_group_permission(request, ['user']):
        return False
    if row is None:
        return True
    if row.household_id is None or row.household.space_id != request.space.pk:
        return False
    return can_manage(request) or household.pk == row.household_id


def menu_choices(request):
    require_professional(request.space)
    choices = []
    for template in visible_templates(request):
        groups = defaultdict(list)
        for entry in template.entries.all():
            groups[(entry.day_index, entry.meal_type_id)].append(entry)
        for (day, meal), entries in groups.items():
            # Production requires real recipes in every dish; a title-only menu
            # cannot silently become a stock-free confirmed reservation.
            if any(not entry.recipe_id for entry in entries):
                continue
            choices.append({'template': template.pk, 'template_name': template.name,
                            'template_day': day, 'meal_type': meal, 'meal_type_name': entries[0].meal_type.name,
                            'dishes': [{'recipe_id': entry.recipe_id, 'recipe_name': entry.recipe.name,
                                        'course_name': entry.course.name if entry.course else '',
                                        'course_id': entry.course_id} for entry in entries]})
    return choices


def select_menu(request, template, day, meal):
    choice = next((row for row in menu_choices(request)
                   if (row['template'], row['template_day'], row['meal_type']) == (template, day, meal)), None)
    if choice is None:
        raise ValidationError({'menu': 'Elige un día y servicio con recetas autorizadas de la plantilla.'})
    choice = deepcopy(choice)
    choice['fingerprint'] = hashlib.sha256(json.dumps(choice, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return choice


def visible_reservations(request, *, reservation_id=None, dates=None):
    """Read across the Space, preserving current native ACLs for frozen dishes."""
    allowed = set(visible_recipes(request.user, request.space).values_list('pk', flat=True))
    rows = CustomerReservation.objects.filter(space=request.space)
    if reservation_id is not None:
        rows = rows.filter(pk=reservation_id)
    for key, value in (dates or {}).items():
        rows = rows.filter(**{key: value})
    if rows.count() > 2000:
        raise ValidationError({'period': 'Hay más de 2000 reservas; reduce el periodo.'})
    rows = rows.select_related('template', 'meal_type', 'household').prefetch_related('history', 'service_links__service')
    ids = []
    for row in rows:
        required = set()
        snapshots = [row.menu_snapshot]
        snapshots += [revision.before.get('menu_snapshot', {}) for revision in row.history.all()]
        snapshots += [revision.after.get('menu_snapshot', {}) for revision in row.history.all()]
        valid = True
        for snapshot in snapshots:
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get('dishes', []), list):
                valid = False; break
            for dish in snapshot.get('dishes', []):
                if not isinstance(dish, dict) or type(dish.get('recipe_id')) is not int:
                    valid = False; break
                required.add(dish['recipe_id'])
        for link in row.service_links.all():
            snapshot = link.service.snapshot or {}
            graph = snapshot.get('recipe_graph', {})
            try:
                for parent, children in graph.items():
                    required.add(int(parent)); required.update(children)
            except (TypeError, ValueError, AttributeError):
                valid = False
        if valid and required.issubset(allowed):
            ids.append(row.pk)
    return rows.filter(pk__in=ids)


def audit_payload(row):
    return {'id': row.pk, 'customer_name': row.customer_name, 'phone': row.phone, 'email': row.email,
            'service_date': row.service_date.isoformat(), 'service_time': row.service_time.isoformat(timespec='minutes'),
            'template': row.template_id, 'template_name': row.menu_snapshot.get('template_name', row.template.name),
            'template_day': row.template_day, 'meal_type': row.meal_type_id,
            'meal_type_name': row.menu_snapshot.get('meal_type_name', row.meal_type.name),
            'covers': row.covers, 'note': row.note, 'state': row.state, 'revision': row.revision,
            'menu_snapshot': deepcopy(row.menu_snapshot)}


def reservation_payload(request, row, *, detail=True):
    result = audit_payload(row)
    operate = can_operate(request, row)
    result.update(can_operate=operate, can_edit=operate and row.state in ('requested', 'confirmed'),
                  can_change_menu=operate and can_manage(request) and row.state in ('requested', 'confirmed'),
                  can_cancel=operate and can_manage(request) and row.state not in ('served', 'cancelled'))
    result['services'] = [serialize_service_plan(link.service) for link in row.service_links.all() if link.active]
    if detail:
        result['history'] = [{'revision': rev.revision, 'action': rev.action, 'reason': rev.reason,
                              'before': rev.before, 'after': rev.after, 'created_at': rev.created_at.isoformat(),
                              'created_by': rev.created_by_id} for rev in row.history.order_by('revision')]
    return result


def check_revision(row, supplied):
    if supplied != row.revision:
        raise Conflict('La reserva ha cambiado. Recarga antes de continuar.')


def record(row, user, action, reason, before):
    row.updated_by = user
    row.save()
    ReservationRevision.objects.create(reservation=row, revision=row.revision, action=action,
                                       reason=reason, before=before, after=audit_payload(row), created_by=user)
    row.refresh_from_db()


def retire_services(row, user):
    for link in row.service_links.select_related('service').filter(active=True).order_by('position', 'pk'):
        plan = link.service
        if plan.state == ServicePlan.PRODUCED:
            reverse_service_plan(plan, user, f'reservation-{row.pk}-cancel-{row.revision}-{plan.pk}')
        else:
            cancel_service_plan(plan)
        link.active = False
        link.save(update_fields=['active'])


def seed_services(row, user):
    start = timezone.make_aware(datetime.combine(row.service_date, row.service_time), timezone.get_current_timezone())
    for position, dish in enumerate(row.menu_snapshot['dishes']):
        meal = MealPlan.objects.create(space=row.space, recipe_id=dish['recipe_id'], meal_type=row.meal_type,
                                       servings=row.covers, title=f'Reserva {row.pk}'[:64], note='',
                                       from_date=start, to_date=start, created_by=user)
        plan = ServicePlan.objects.create(space=row.space, household=row.household, meal_plan=meal,
                                          title=f'Reserva {row.pk} · {row.customer_name}'[:128], covers=row.covers,
                                          service_date=row.service_date, created_by=user)
        ReservationService.objects.create(reservation=row, service=plan, revision=row.revision,
                                          position=position, active=True)
        confirm_service_plan(plan, user)


def require_household(request, row=None):
    household = getattr(getattr(request, 'user_space', None), 'household', None)
    if household is None or household.space_id != request.space.pk:
        raise ValidationError({'household': 'Asigna un hogar operativo antes de gestionar reservas.'})
    if row is not None and not can_operate(request, row):
        raise PermissionDenied('Solo puedes operar reservas del hogar asignado.')
    return household


@transaction.atomic
def create_reservation(request, data):
    lock_space(request); require_professional(request.space)
    household = require_household(request)
    menu = select_menu(request, data['template'], data['template_day'], data['meal_type'])
    reason = data.pop('reason')
    row = CustomerReservation.objects.create(space=request.space, household=household, created_by=request.user,
        updated_by=request.user, menu_snapshot=menu, template_id=data.pop('template'), meal_type_id=data.pop('meal_type'), **data)
    record(row, request.user, 'create', reason, {})
    return row


@transaction.atomic
def update_reservation(request, reservation_id, data):
    lock_space(request); require_professional(request.space)
    row = get_object_or_404(visible_reservations(request, reservation_id=reservation_id).select_for_update(of=('self',)), pk=reservation_id)
    require_household(request, row); check_revision(row, data.pop('revision'))
    if row.state not in ('requested', 'confirmed'):
        raise Conflict('Solo se pueden editar reservas solicitadas o confirmadas.')
    reason = data.pop('reason')
    before = audit_payload(row)
    if MENU_FIELDS.intersection(data):
        if not can_manage(request):
            raise PermissionDenied('Solo Responsable puede cambiar el menú.')
        row.menu_snapshot = select_menu(request, data.get('template', row.template_id),
                                        data.get('template_day', row.template_day), data.get('meal_type', row.meal_type_id))
    for name, value in data.items():
        setattr(row, name + '_id' if name in ('template', 'meal_type') else name, value)
    if not (row.phone.strip() or row.email.strip()):
        raise ValidationError({'contact': 'Indica teléfono o email.'})
    row.revision += 1
    reseed = any(before.get(name) != (getattr(row, name + '_id') if name in ('template', 'meal_type') else getattr(row, name).isoformat() if name == 'service_date' else getattr(row, name).isoformat(timespec='minutes') if name == 'service_time' else getattr(row, name))
                 for name in ('template', 'template_day', 'meal_type', 'covers', 'service_date', 'service_time'))
    reseed = reseed or before['menu_snapshot'] != row.menu_snapshot
    if row.state == 'confirmed' and reseed:
        retire_services(row, request.user); seed_services(row, request.user)
    record(row, request.user, 'edit', reason, before)
    return row


@transaction.atomic
def transition_reservation(request, reservation_id, data):
    lock_space(request); require_professional(request.space)
    row = get_object_or_404(visible_reservations(request, reservation_id=reservation_id).select_for_update(of=('self',)), pk=reservation_id)
    require_household(request, row)
    action = data['action']
    target = {'confirm': 'confirmed', 'start_kitchen': 'in_kitchen', 'serve': 'served', 'cancel': 'cancelled'}[action]
    if action == 'cancel' and not can_manage(request):
        raise PermissionDenied('Solo Responsable puede cancelar reservas.')
    # A replay of the immediately committed intention is read-only; all other
    # stale requests conflict, including a competing action at that revision.
    if row.state == target and data['revision'] == row.revision - 1:
        latest = row.history.order_by('-revision').first()
        if latest and latest.action == action and latest.reason == data['reason']:
            return row
    check_revision(row, data['revision'])
    permitted = {'confirm': ('requested',), 'start_kitchen': ('confirmed',),
                 'serve': ('in_kitchen',), 'cancel': ('requested', 'confirmed', 'in_kitchen')}
    if row.state not in permitted[action]:
        raise Conflict('La reserva no admite esta transición.')
    before = audit_payload(row); row.revision += 1
    if action == 'confirm':
        seed_services(row, request.user)
    elif action == 'start_kitchen':
        links = list(row.service_links.select_related('service').filter(active=True).order_by('position', 'pk'))
        if len(links) != len(row.menu_snapshot['dishes']):
            raise Conflict('La ficha de producción no coincide con el menú confirmado.')
        for link in links:
            produce_service_plan(link.service, request.user, f'reservation-{row.pk}-produce-{link.revision}-{link.service_id}')
    elif action == 'cancel':
        retire_services(row, request.user)
    row.state = target
    record(row, request.user, action, data['reason'], before)
    return row


def reservation_summary(request, service_date):
    groups = {}
    for row in visible_reservations(request, dates={'service_date': service_date}).filter(state__in=('confirmed', 'in_kitchen')).order_by('pk'):
        menu = row.menu_snapshot
        key = (row.template_id, row.template_day, row.meal_type_id, menu.get('fingerprint'))
        if key not in groups:
            groups[key] = {'template': row.template_id, 'template_name': menu.get('template_name'),
                           'template_day': row.template_day, 'meal_type': row.meal_type_id,
                           'meal_type_name': menu.get('meal_type_name'), 'menu_fingerprint': menu.get('fingerprint'),
                           'confirmed_covers': 0, 'in_kitchen_covers': 0, 'pending_covers': 0,
                           'total_active_covers': 0, 'reservations': [], 'dishes': [], 'needs': [],
                           'warnings': [], 'service_ids': [], '_needs': {}, '_dishes': {}}
        group = groups[key]
        group[row.state + '_covers'] += row.covers
        group['total_active_covers'] += row.covers
        group['reservations'].append(row.pk)
        for link in row.service_links.all():
            if not link.active:
                continue
            group['service_ids'].append(link.service_id)
            snapshot = link.service.snapshot
            group['warnings'].extend(snapshot.get('warnings', []))
            dish = menu['dishes'][link.position]
            dish_key = (link.position, dish['recipe_id'])
            accumulated = group['_dishes'].setdefault(dish_key, {
                'recipe_id': dish['recipe_id'], 'recipe_name': dish['recipe_name'],
                'course_name': dish.get('course_name', ''), 'position': link.position,
                'pending_servings': 0, 'in_kitchen_servings': 0, 'total_active_servings': 0})
            accumulated['total_active_servings'] += row.covers
            accumulated['pending_servings' if row.state == 'confirmed' else 'in_kitchen_servings'] += row.covers
            # Production sheets list only remaining work; produced reservations
            # remain visible separately and cannot add their ingredients twice.
            if row.state != 'confirmed':
                continue
            for need in snapshot.get('needs', []):
                need_key = (need.get('food_id'), need.get('unit_id'))
                accumulated_need = group['_needs'].setdefault(need_key, {
                    'food_id': need.get('food_id'), 'food_name': need.get('food_name', ''),
                    'unit_id': need.get('unit_id'), 'unit_name': need.get('unit_name', ''), 'quantity': Decimal('0')})
                with localcontext() as context:
                    context.prec = 80
                    accumulated_need['quantity'] += Decimal(need['quantity'])
    for group in groups.values():
        group['pending_covers'] = group['confirmed_covers']
        group['dishes'] = list(group.pop('_dishes').values())
        group['needs'] = [{**need, 'quantity': format(need['quantity'], 'f')}
                          for need in group.pop('_needs').values()]
    return {'date': service_date.isoformat(), 'groups': list(groups.values()),
            'pending_covers': sum(group['pending_covers'] for group in groups.values()),
            'total_active_covers': sum(group['total_active_covers'] for group in groups.values()),
            'in_kitchen_covers': sum(group['in_kitchen_covers'] for group in groups.values())}
