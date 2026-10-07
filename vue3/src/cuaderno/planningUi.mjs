export function dietPresentation(status) {
    if (status === 'suitable') return {label: 'Apto · declaración manual', color: 'success'}
    if (status === 'unsuitable') return {label: 'No apto · declaración manual', color: 'error'}
    return {label: 'No declarado', color: 'warning'}
}

function dateNumber(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Fecha no válida.')
    const time = Date.parse(value + 'T00:00:00Z')
    if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 10) !== value) throw new Error('Fecha no válida.')
    return time
}

export function planningEndDate(start, weeks) {
    if (!Number.isInteger(weeks) || weeks < 1 || weeks > 5) throw new Error('Elige entre una y cinco semanas.')
    return new Date(dateNumber(start) + (weeks * 7 - 1) * 86400000).toISOString().slice(0, 10)
}

export function templateEntriesFromPlans(plans, start, weeks) {
    planningEndDate(start, weeks)
    if (!Array.isArray(plans) || plans.length > 200) throw new Error('La plantilla admite hasta 200 platos.')
    return plans.map(plan => {
        const from = String(plan.from_date).slice(0, 10)
        const day = (dateNumber(from) - dateNumber(start)) / 86400000
        if (day < 0 || day >= weeks * 7) throw new Error('Hay platos fuera del periodo de la plantilla.')
        if (plan.to_date && String(plan.to_date).slice(0, 10) !== from) throw new Error('Divide las entradas de varios días antes de guardarlas como plantilla.')
        return {day_index: day, meal_type: plan.meal_type.id, course: plan.course ?? null,
            recipe: plan.recipe?.id ?? null, title: plan.title || '', source_url: plan.source_url || '', servings: String(plan.servings)}
    })
}
