"""Prospective prices run through the same Decimal/subrecipe engine, in memory."""
from dataclasses import replace
from decimal import Decimal, localcontext
from types import SimpleNamespace
from django.utils import timezone
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal
from cuaderno.services.costing import _load_costing_context, visible_recipes
from cuaderno.services.price_history import _cost_sheet, _TrackingPrices
from cuaderno.services.subrecipes import native_recipe_graph


def price_simulation(request, rows, recipe_id=None, servings=None):
    proposed={row['package_id']:SimpleNamespace(amount=Decimal(row['amount']),explicit_free=row['explicit_free']) for row in rows}
    recipes=visible_recipes(request.user,request.space).order_by('pk')
    if recipe_id: recipes=recipes.filter(pk=recipe_id)
    recipes=list(recipes[:51])
    warnings=[]; items=[]; evidence=[]
    if len(recipes)>50:
        warnings.append('Simulación limitada a las primeras 50 recetas visibles; filtra una receta para revisar más. No es un análisis completo del catálogo.')
    at=timezone.now()
    for recipe in recipes[:50]:
        try:
            roots,graph,_=native_recipe_graph([recipe.pk],request.space.pk,request.user)
            context=_load_costing_context(graph,request.space.pk,at)
            with localcontext() as decimal_context:
                decimal_context.prec=64
                tracked=_TrackingPrices(context.prices)
                base=recipe.servings or 1
                if base<=0: raise DomainError('invalid_servings','Raciones base inválidas.')
                target=parse_decimal(servings,allow_zero=False) if servings is not None else Decimal(base)
                before=_cost_sheet(roots[0],at,base,target,replace(context,prices=tracked))
                if not proposed.keys() & tracked.read_keys: continue
                after=_cost_sheet(roots[0],at,base,target,replace(context,prices={**context.prices,**proposed}))
                difference=None
                if before['status']==after['status']=='complete':
                    difference=format(Decimal(after['unrounded'])-Decimal(before['unrounded']),'f')
            items.append({'title':recipe.name,'detail':'Simulación del precio propuesto; todavía no se ha guardado.',
                'action_url':f'/recipe/{recipe.pk}', 'values':{'recipe_id':recipe.pk,'before':before,'after':after,'difference':difference},
                'type':'proposed_price_impact','recipe_id':recipe.pk})
            evidence.extend({'type':'recipe','id':source.pk,'label':source.name} for source in graph.values())
        except DomainError:
            warnings.append(f'No se pudo simular la receta visible {recipe.pk}; revisa sus datos antes de decidir.')
    return items,evidence,warnings
