"""Deterministic, local worker proposals with explicit approval and readback.

No network fetching, generated code, model calls, or implicit stock movements.
Business mutations are delegated to the existing services in one transaction.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal, localcontext
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from cookbook.helper.permission_helper import has_group_permission
from cookbook.models import Recipe, Step, Ingredient, Unit, UnitConversion, InventoryEntry
from cuaderno import models
from cuaderno.api.purchasing import DecimalStringField, OrderWriteSerializer
from cuaderno.domain.money import canonical_decimal
from cuaderno.services.profiles import profile_for_space
from cuaderno.services.purchasing import accessible_offers, create_order, serialize_order
from cuaderno.services.visibility import visible_packages

POLICY = {'version':'cuaderno-local-workers-v1', 'require_approval':True,
          'approval_role':'admin', 'external_services':False, 'unknown_is_zero':False,
          'allergen_absence_inferred':False, 'actions':['reference_prices','purchase_draft'],
          'max_price_rows':50, 'evidence_required':True}
KINDS = [
    {'id':'cost_completion','title':'Completar costes','description':'Agrupa datos que faltan y muestra cómo resolverlos.','min_edition':'esencial'},
    {'id':'price_watch','title':'Vigilar precios','description':'Revisa cambios y prepara precios con evidencia.','min_edition':'esencial'},
    {'id':'service_briefing','title':'Preparar el servicio','description':'Reúne reservas, necesidades y preparación del día.','min_edition':'profesional'},
    {'id':'requirements_review','title':'Revisar requisitos','description':'Señala declaraciones desconocidas y notas que necesitan revisión.','min_edition':'profesional'},
    {'id':'purchase_review','title':'Preparar compras','description':'Revisa necesidades, existencias y pedidos pendientes.','min_edition':'integral'},
    {'id':'receipt_review','title':'Revisar entregas','description':'Contrasta cantidades pedidas y recepciones registradas.','min_edition':'integral'},
    {'id':'menu_candidates','title':'Proponer platos','description':'Compara recetas existentes por coste y disponibilidad.','min_edition':'profesional'},
    {'id':'service_learning','title':'Aprender del registro','description':'Revisa incidencias y datos registrados sin inventar resultados.','min_edition':'profesional'},
]

class WorkerConflict(APIException):
    status_code = 409
    default_detail = 'Los datos han cambiado. Genera y revisa una propuesta nueva.'
    default_code = 'worker_conflict'


def _canonical(value):
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(',',':'), ensure_ascii=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _json(value):
    return json.loads(_canonical(value))


def _identifier(value, field):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or int(value) <= 0:
        raise ValidationError({field:'Indica un identificador entero positivo.'})
    return int(value)


def _check_kind(request, kind):
    definition = next((row for row in KINDS if row['id']==kind), None)
    if definition is None:
        raise ValidationError({'kind':'Trabajador desconocido.'})
    edition = profile_for_space(request.space).edition
    rank = {'esencial':0,'profesional':1,'integral':2}
    if rank.get(edition,-1) < rank[definition['min_edition']]:
        raise PermissionDenied('Esta tarea necesita la edición '+definition['min_edition']+'.')
    return definition


def _csv_rows(raw):
    if not isinstance(raw,str) or len(raw)>50000:
        raise ValidationError({'csv':'El CSV admite hasta 50 KB y 50 filas.'})
    try:
        reader = csv.DictReader(io.StringIO(raw.lstrip('\ufeff')), strict=True)
        fields = reader.fieldnames or []
        if len(set(fields)) != len(fields) or not {'package_id','amount'} <= set(fields) or set(fields)-{'package_id','amount','explicit_free','note'}:
            raise ValidationError({'csv':'Columnas: package_id,amount,explicit_free,note. Usa IDs del catálogo.'})
        rows=[]
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValidationError({'csv':'Número de columnas incorrecto.'})
            flag=row.get('explicit_free','false').strip().lower()
            if flag not in ('true','false',''):
                raise ValidationError({'csv':'explicit_free debe ser true o false.'})
            row['explicit_free']=flag=='true'
            rows.append(row)
            if len(rows)>50:
                raise ValidationError({'csv':'Máximo 50 filas por propuesta.'})
        return rows
    except csv.Error as exc:
        raise ValidationError({'csv':'CSV inválido.'}) from exc


def _proposal(request, kind, raw):
    if not raw:
        return {}
    if not isinstance(raw,dict) or set(raw)-{'action','payload'}:
        raise ValidationError({'proposal':'Indica una acción y sus datos.'})
    action=raw.get('action')
    payload=raw.get('payload')
    if action not in POLICY['actions'] or not isinstance(payload,dict):
        raise ValidationError({'proposal':'Acción no permitida.'})
    evidence=payload.get('evidence','')
    if not isinstance(evidence,str) or not 5<=len(evidence.strip())<=4000:
        raise ValidationError({'evidence':'Describe la fuente revisada (5–4000 caracteres); no incluyas datos personales.'})
    evidence=evidence.strip()
    if action=='reference_prices':
        if kind!='price_watch':
            raise ValidationError({'proposal':'Los precios se revisan con Vigilar precios.'})
        if set(payload)-{'rows','csv','evidence'}:
            raise ValidationError({'proposal':'Campos desconocidos.'})
        rows=payload.get('rows')
        if payload.get('csv'):
            if rows:
                raise ValidationError({'csv':'Envía filas o CSV, no ambos.'})
            rows=_csv_rows(payload['csv'])
        if not isinstance(rows,list) or not 1<=len(rows)<=50:
            raise ValidationError({'rows':'Indica entre 1 y 50 precios.'})
        normalized=[]; effects=[]; seen=set()
        for row in rows:
            if not isinstance(row,dict) or set(row)-{'package_id','amount','explicit_free','note'}:
                raise ValidationError({'rows':'Fila de precio inválida.'})
            pk=_identifier(row.get('package_id'),'package_id')
            if pk in seen:
                raise ValidationError({'rows':'Un formato no puede repetirse en la misma propuesta.'})
            seen.add(pk)
            package=get_object_or_404(visible_packages(request.user,request.space).select_related('food','unit'),pk=pk)
            amount=DecimalStringField(allow_zero=True).run_validation(row.get('amount'))
            free=row.get('explicit_free',False)
            if type(free) is not bool or (amount==0)!=free:
                raise ValidationError({'explicit_free':'Solo el cero se declara gratuito y debe confirmarse expresamente.'})
            note=row.get('note','')
            if not isinstance(note,str) or len(note)>256:
                raise ValidationError({'note':'La nota admite hasta 256 caracteres.'})
            normalized.append({'package_id':pk,'amount':canonical_decimal(amount),'explicit_free':free,'note':note})
            old=models.PriceVersion.objects.filter(package=package,space=request.space,valid_from__lte=timezone.now()).order_by('-valid_from','-pk').first()
            old_label=canonical_decimal(old.amount) if old else 'desconocido'
            effects.append(f'{package.food.name} · {package.label}: {old_label} → {canonical_decimal(amount)} {profile_for_space(request.space).currency} por {canonical_decimal(package.quantity)} {package.unit.name}.')
        effects.append('Se añadirán versiones de precio de referencia. No cambia el stock, las ofertas ni las fichas de servicio ya confirmadas.')
        return {'action':action,'label':'Aprobar y registrar precios','payload':{'rows':normalized,'evidence':evidence},'effects':effects}
    if kind!='purchase_review' or profile_for_space(request.space).edition!='integral':
        raise PermissionDenied('Los borradores de compra necesitan Integral y Preparar compras.')
    if set(payload)-{'package_id','package_count','offer_id','evidence','household_id'}:
        raise ValidationError({'proposal':'Campos desconocidos.'})
    pk=_identifier(payload.get('package_id'),'package_id')
    package=get_object_or_404(visible_packages(request.user,request.space).select_related('food','unit'),pk=pk)
    count=DecimalStringField().run_validation(payload.get('package_count'))
    if count!=count.to_integral_value():
        raise ValidationError({'package_count':'El borrador del trabajador pide envases completos.'})
    with localcontext() as context:
        context.prec=64
        quantity=canonical_decimal(package.quantity*count)
    data={'package':pk,'package_count':canonical_decimal(count),'quantity':quantity}
    offer_id=payload.get('offer_id')
    offer=None
    if offer_id not in (None,''):
        offer_id=_identifier(offer_id,'offer_id')
        offer=get_object_or_404(accessible_offers(request.user,request.space).select_related('supplier'),pk=offer_id,package=package)
        if offer.valid_from>timezone.now():
            raise ValidationError({'offer_id':'La oferta aún no está vigente.'})
        if offer.currency!=profile_for_space(request.space).currency:
            raise ValidationError({'offer_id':'La moneda de la oferta no coincide con la del espacio.'})
        data['offer']=offer_id
    serializer=OrderWriteSerializer(data=data); serializer.is_valid(raise_exception=True)
    from cuaderno.services.purchasing import _membership_household
    household_id=payload.get('household_id')
    if household_id is not None: household_id=_identifier(household_id,'household_id')
    household=_membership_household(request,household_id)
    normalized={'package_id':pk,'package_count':canonical_decimal(count),'evidence':evidence,'household_id':household.pk}
    if offer_id: normalized['offer_id']=offer_id
    total='Precio desconocido; pendiente de elegir una oferta.'
    if offer:
        with localcontext() as context:
            context.prec=64
            total=f'{offer.supplier.name}: {canonical_decimal(offer.amount*count)} {offer.currency}.'
    return {'action':action,'label':'Aprobar y crear borrador','payload':normalized,'effects':[
        f'Crear un borrador para {household.name} de {canonical_decimal(count)} envases de {package.food.name}: {quantity} {package.unit.name}.',total,
        'No se envía al proveedor ni se recibe mercancía. El stock no cambia. Revisa los pedidos abiertos antes de aprobar.']}


def _state_digest(request):
    """Conservative bounded invalidation includes native M2M and operational data.

    Hash only; no hidden rows/labels are persisted or returned. The broad scope
    deliberately prefers requiring a new approval over applying stale inputs.
    """
    digest=hashlib.sha256()
    from django.apps import apps
    classes=[Recipe,Step,Ingredient,Unit,UnitConversion,InventoryEntry]
    classes += [model for model in apps.get_app_config('cuaderno').get_models()
                if model not in (models.WorkerRun,models.WorkerEvent,models.WorkerSchedule) and any(f.name=='space' for f in model._meta.fields)]
    from cookbook.models import Food, Supermarket, InventoryLocation, MealPlan, UserSpace
    classes += [Food,Supermarket,InventoryLocation,MealPlan,UserSpace]
    total=0
    for model in classes:
        digest.update(model._meta.label.encode())
        for row in model._base_manager.filter(space=request.space).order_by('pk').values().iterator(chunk_size=500):
            total+=1
            if total>50000:
                raise ValidationError({'scope':'Demasiados datos para aprobar de forma segura en esta versión. Usa el flujo manual.'})
            digest.update(_canonical(row).encode())
    for relation,field in ((Recipe.steps.through,'recipe'),(Step.ingredients.through,'step')):
        digest.update(relation._meta.label.encode())
        for row in relation.objects.filter(**{field+'__space':request.space}).order_by('pk').values().iterator(chunk_size=500):
            total+=1
            if total>50000: raise ValidationError({'scope':'Demasiadas relaciones para esta propuesta.'})
            digest.update(_canonical(row).encode())
    # Effective dates matter even when nobody has written since preview.
    current=list(models.PriceVersion.objects.filter(space=request.space,valid_from__lte=timezone.now()).order_by('pk').values_list('pk',flat=True))
    digest.update(_canonical(current).encode())
    return digest.hexdigest()


def _source_digest(request, kind, params, report, proposal):
    return _digest({'state':_state_digest(request),'local_date':timezone.localdate().isoformat(),'kind':kind,'params':params,'proposal':proposal,'policy':POLICY})


def serialize_run(run, *, include_report=True):
    result={'id':run.pk,'kind':run.kind,'title':run.report.get('title',run.kind),'status':run.status,
            'created_at':run.created_at.isoformat(),'summary':run.report.get('summary',''),
            'input_digest':run.input_digest,'evidence_digest':run.evidence_digest,'proposal':run.proposal or None,
            'policy':run.policy,'params':run.params,'result':run.result,'applied_at':run.applied_at.isoformat() if run.applied_at else None,
            'approved_by':run.approved_by_id,'created_by':run.created_by_id}
    if include_report:
        result['report']=run.report
        result['events']=[{'event':event.event,'actor':event.actor_id,'created_at':event.created_at.isoformat(),'data':event.data} for event in run.events.order_by('pk')]
    return result


def owned_run(request, pk, *, lock=False):
    rows=models.WorkerRun.objects.filter(space=request.space)
    if not has_group_permission(request,['admin']): rows=rows.filter(created_by=request.user)
    if lock: rows=rows.select_for_update()
    return get_object_or_404(rows,pk=pk)


def _reauthorize(request, run):
    """Authorize stored source IDs directly; analysis output is not an ACL."""
    _check_kind(request,run.kind)
    audience=run.report.get('audience',{})
    if audience and not has_group_permission(request,['admin']):
        own_household=getattr(getattr(request,'user_space',None),'household_id',None)
        if audience.get('admin_oversight') or audience.get('household_id')!=own_household:
            raise PermissionDenied('El ámbito del hogar del informe ha cambiado.')
    from collections import defaultdict
    from cuaderno.services.costing import visible_recipes
    from cuaderno.services.visibility import visible_foods
    from cuaderno.services.purchasing import accessible_orders
    from cuaderno.services.reservations import visible_reservations
    from cuaderno.services.service_plans import accessible_service_plans
    from cuaderno.services.inventory_access import household_inventory
    refs=defaultdict(set)
    aliases={'recipe_id':'recipe','package_id':'package','order_id':'order','service_id':'service',
             'reservation_id':'reservation','food_id':'food','unit_id':'unit','entry_id':'entry'}
    def collect(value):
        if isinstance(value,dict):
            if value.get('type') in set(aliases.values()) and type(value.get('id')) is int:
                refs[value['type']].add(value['id'])
            for key,item in value.items():
                if key in aliases and type(item) is int: refs[aliases[key]].add(item)
                elif key=='foods' and isinstance(item,list):
                    refs['food'].update(row['id'] for row in item if isinstance(row,dict) and type(row.get('id')) is int)
                elif key in ('inventory_entry_ids','service_ids') and isinstance(item,list):
                    refs['entry' if key=='inventory_entry_ids' else 'service'].update(i for i in item if type(i) is int)
                collect(item)
        elif isinstance(value,list):
            for item in value: collect(item)
    collect(run.report)
    collect(run.result)
    if run.result.get('action')=='purchase_draft' and isinstance(run.result.get('order'),dict):
        refs['order'].add(run.result['order']['id'])
    queries={'recipe':visible_recipes(request.user,request.space),'package':visible_packages(request.user,request.space),
             'food':visible_foods(request.user,request.space),'unit':Unit.objects.filter(space=request.space),
             'order':accessible_orders(request),'entry':household_inventory(request,InventoryEntry.objects.all())}
    for kind, ids in refs.items():
        if kind=='service':
            allowed=set(accessible_service_plans(request,aggregate_filters={'pk__in':ids}).values_list('pk',flat=True))
        elif kind=='reservation':
            allowed=set(visible_reservations(request,dates={'pk__in':ids}).values_list('pk',flat=True))
        else:
            allowed=set(queries[kind].filter(pk__in=ids).values_list('pk',flat=True))
        if not ids<=allowed:
            raise PermissionDenied('Una fuente ya no está disponible. Genera un informe nuevo.')
    if run.proposal:
        _proposal(request,run.kind,{'action':run.proposal['action'],'payload':run.proposal['payload']})


def _refresh_actor(request, role):
    from cookbook.models import UserSpace
    membership=UserSpace.objects.filter(user=request.user,space=request.space,active=True).first()
    if membership is None:
        raise PermissionDenied('La pertenencia al espacio ha cambiado.')
    request.user_space=membership
    if not has_group_permission(request,[role],no_cache=True):
        raise PermissionDenied('Tus permisos han cambiado. Vuelve a abrir la tarea.')


@transaction.atomic
def preview(request, data):
    type(request.space).objects.select_for_update().get(pk=request.space.pk)
    _refresh_actor(request,'user')
    kind=data.get('kind'); _check_kind(request,kind)
    params=data.get('params',{})
    if not isinstance(params,dict) or len(_canonical(params))>8000:
        raise ValidationError({'params':'Parámetros inválidos o demasiado largos.'})
    proposal=_proposal(request,kind,data.get('proposal'))
    from cuaderno.services.worker_analysis import build_worker_report
    report=_json(build_worker_report(request,kind,params))
    if kind in ('purchase_review','receipt_review','menu_candidates'):
        report['audience']={'household_id':getattr(request.user_space,'household_id',None),'admin_oversight':has_group_permission(request,['admin'])}
    if proposal.get('action')=='reference_prices':
        from cuaderno.services.worker_price_simulation import price_simulation
        items,evidence,warnings=price_simulation(request,proposal['payload']['rows'],params.get('recipe_id'),params.get('servings'))
        report['items']=items+report['items']
        report['evidence'].extend(row for row in evidence if row not in report['evidence'])
        report['warnings'].extend(warnings)
        report['summary']=f"{len(items)} recetas con impacto de la propuesta en la selección analizada. Precios sin guardar hasta aprobar."
    if len(_canonical(report))>500000:
        raise ValidationError({'report':'Demasiados resultados. Selecciona una receta o reduce el límite.'})
    # Reports save evidence only. No business writes occur until apply.
    run=models.WorkerRun.objects.create(space=request.space,created_by=request.user,kind=kind,params=params,report=report,
        proposal=proposal,policy=POLICY,status='pending' if proposal else 'read_only',
        input_digest=_source_digest(request,kind,params,report,proposal),evidence_digest=_digest({'report':report,'proposal':proposal,'policy':POLICY}))
    models.WorkerEvent.objects.create(run=run,actor=request.user,event='previewed',data={'evidence_digest':run.evidence_digest})
    return run


def apply(request, pk, data):
    if data.get('approval') is not True:
        raise ValidationError({'approval':'Confirma expresamente la acción y sus efectos.'})
    if not has_group_permission(request,['admin']):
        raise PermissionDenied('Solo Responsable puede aprobar propuestas de trabajadores.')
    stale=False
    with transaction.atomic():
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        _refresh_actor(request,'admin')
        run=owned_run(request,pk,lock=True)
        _check_kind(request,run.kind)
        if data.get('expected_digest')!=run.input_digest:
            raise WorkerConflict('La aprobación no corresponde a esta propuesta.')
        _reauthorize(request,run)
        if run.status=='applied': return run
        if run.status!='pending': raise WorkerConflict('La propuesta ya no está pendiente. Genera otra.')
        proposal=_proposal(request,run.kind,{'action':run.proposal['action'],'payload':run.proposal['payload']})
        if run.policy!=POLICY or _source_digest(request,run.kind,run.params,run.report,proposal)!=run.input_digest:
            run.status='stale'; run.save(update_fields=['status'])
            models.WorkerEvent.objects.create(run=run,actor=request.user,event='stale',data={'reason':'source_or_policy_changed'})
            stale=True
        else:
            payload=proposal['payload']
            if proposal['action']=='reference_prices':
                ids=[]
                for row in payload['rows']:
                    price=models.PriceVersion.objects.create(space=request.space,package_id=row['package_id'],amount=Decimal(row['amount']),
                        explicit_free=row['explicit_free'],valid_from=timezone.now(),created_by=request.user,note=row['note'])
                    ids.append(price.pk)
                # Read back persisted exact values, not the submitted form.
                result={'action':'reference_prices','price_ids':ids,'prices':list(models.PriceVersion.objects.filter(pk__in=ids).order_by('pk').values('id','package_id','amount','explicit_free')),'stock_changed':False}
            else:
                package=get_object_or_404(visible_packages(request.user,request.space),pk=payload['package_id'])
                with localcontext() as context:
                    context.prec=64
                    quantity=canonical_decimal(package.quantity*Decimal(payload['package_count']))
                data={'package':package.pk,'package_count':payload['package_count'],'quantity':quantity}
                if payload.get('offer_id'): data['offer']=payload['offer_id']
                serializer=OrderWriteSerializer(data=data); serializer.is_valid(raise_exception=True)
                order=create_order(request=request,data={**serializer.validated_data,'household':payload['household_id']}); order.refresh_from_db()
                result={'action':'purchase_draft','order':serialize_order(order),'stock_changed':False,'sent_to_supplier':False}
            run.status='applied'; run.approved_by=request.user; run.applied_at=timezone.now(); run.result=_json(result)
            run.save(update_fields=['status','approved_by','applied_at','result'])
            models.WorkerEvent.objects.create(run=run,actor=request.user,event='approved_and_applied',data=run.result)
    if stale: raise WorkerConflict()
    return run


@transaction.atomic
def dismiss(request, pk):
    type(request.space).objects.select_for_update().get(pk=request.space.pk)
    _refresh_actor(request,'user')
    run=owned_run(request,pk,lock=True)
    if run.status=='applied': raise WorkerConflict('Una acción aplicada conserva su registro; corrígela con una operación nueva.')
    if run.status!='dismissed':
        run.status='dismissed'; run.save(update_fields=['status'])
        models.WorkerEvent.objects.create(run=run,actor=request.user,event='dismissed')
    return run
