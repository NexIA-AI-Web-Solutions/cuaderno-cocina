export type ReservationState = 'requested' | 'confirmed' | 'in_kitchen' | 'served' | 'cancelled';
export type ReservationAction = 'confirm' | 'start_kitchen' | 'serve' | 'cancel';
export type MenuChoice = {
    template: number;
    template_name?: string;
    template_day: number;
    meal_type: number;
    meal_type_name?: string;
    dishes?: {
        recipe_id: number;
        recipe_name: string;
        course_name?: string | null;
    }[];
};
export type ReservationDraft = {
    customer_name: string;
    phone: string;
    email: string;
    service_date: string;
    service_time: string;
    covers: string;
    note: string;
    reason: string;
    menu: MenuChoice | null;
};
export type ReservationHistory = {
    revision: number;
    action: string;
    reason: string;
    before: unknown;
    after: unknown;
    created_at: string;
};
export type ReservationRow = {
    id: number;
    customer_name: string;
    phone: string;
    email: string;
    service_date: string;
    service_time: string;
    template: number;
    template_name: string;
    template_day: number;
    meal_type: number;
    meal_type_name: string;
    covers: number;
    note: string;
    state: ReservationState;
    revision: number;
    can_operate: boolean;
    can_edit: boolean;
    can_change_menu: boolean;
    can_cancel: boolean;
    menu_snapshot?: {
        dishes?: {
            recipe_id: number;
            recipe_name: string;
            course_name?: string | null;
        }[];
    };
    services?: {
        id: number;
        state: string;
    }[];
    history?: ReservationHistory[];
};
export type ReservationSummary = {
    date: string;
    pending_covers: number;
    total_active_covers: number;
    in_kitchen_covers: number;
    groups: {
        menu_fingerprint: string;
        template: number;
        template_day: number;
        meal_type: number;
        template_name: string;
        meal_type_name: string;
        confirmed_covers: number;
        in_kitchen_covers: number;
        pending_covers: number;
        total_active_covers: number;
        reservations: number[];
        dishes: {
            recipe_id: number;
            recipe_name: string;
            course_name?: string | null;
            pending_servings: number;
            in_kitchen_servings: number;
            total_active_servings: number;
        }[];
        needs: {
            food_id: number;
            food_name: string;
            unit_id: number | null;
            unit_name: string | null;
            quantity: string;
        }[];
        warnings: {
            code?: string;
        }[];
        service_ids: number[];
    }[];
};
export function menuKey(menu: MenuChoice): string { return `${menu.template}:${menu.template_day}:${menu.meal_type}`; }
export function summaryGroupKey(group: MenuChoice & {menu_fingerprint: string}): string {
    return `${menuKey(group)}:${group.menu_fingerprint}`;
}
export function reservationStateLabel(state: string): string { return ({ requested: 'Solicitada', confirmed: 'Confirmada', in_kitchen: 'En cocina', served: 'Servida', cancelled: 'Anulada' } as Record<string, string>)[state] || 'Estado desconocido'; }
export function reservationActions(state: string, operate: boolean, manage: boolean): ReservationAction[] {
    if (!operate)
        return [];
    const next = ({ requested: 'confirm', confirmed: 'start_kitchen', in_kitchen: 'serve' } as Record<string, ReservationAction>)[state];
    const actions: ReservationAction[] = next ? [next] : [];
    if (manage && ['requested', 'confirmed', 'in_kitchen'].includes(state))
        actions.push('cancel');
    return actions;
}
export function reservationBody(draft: ReservationDraft) {
    const errors: string[] = [];
    const customer_name = draft.customer_name.trim(), phone = draft.phone.trim(), email = draft.email.trim(), reason = draft.reason.trim();
    if (!customer_name || customer_name.length > 160)
        errors.push('Indica un cliente de hasta 160 caracteres.');
    if (!phone && !email)
        errors.push('Indica al menos un teléfono o un correo electrónico.');
    if (phone.length > 64)
        errors.push('El teléfono admite hasta 64 caracteres.');
    if (email && (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254))
        errors.push('Revisa el correo electrónico.');
    const date = /^\d{4}-\d{2}-\d{2}$/.test(draft.service_date) ? new Date(`${draft.service_date}T12:00:00Z`) : null;
    if (!date || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== draft.service_date)
        errors.push('Indica una fecha válida.');
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(draft.service_time))
        errors.push('Indica una hora válida.');
    if (!/^\d{1,4}$/.test(draft.covers.trim()) || Number(draft.covers) < 1 || Number(draft.covers) > 9999)
        errors.push('Los comensales deben ser un entero entre 1 y 9999.');
    if (!draft.menu || !Number.isSafeInteger(draft.menu.template) || draft.menu.template <= 0 || !Number.isSafeInteger(draft.menu.meal_type) || draft.menu.meal_type <= 0 || !Number.isSafeInteger(draft.menu.template_day) || draft.menu.template_day < 0)
        errors.push('Selecciona un menú guardado, día y servicio.');
    if (!reason || reason.length > 1000)
        errors.push('Indica un motivo de hasta 1000 caracteres.');
    if (draft.note.length > 1000)
        errors.push('La nota admite hasta 1000 caracteres.');
    return { errors, body: errors.length || !draft.menu ? null : { customer_name, phone, email, service_date: draft.service_date, service_time: draft.service_time, covers: Number(draft.covers), note: draft.note, reason, template: draft.menu.template, template_day: draft.menu.template_day, meal_type: draft.menu.meal_type } };
}

export function reservationHistoryAction(action: string): string {
    return ({create: 'Reserva registrada', edit: 'Datos editados', update: 'Datos editados', confirm: 'Reserva confirmada', start_kitchen: 'Paso a cocina', serve: 'Reserva servida', cancel: 'Reserva anulada'} as Record<string, string>)[action] || 'Cambio registrado';
}
export function reservationHistoryText(value: unknown): string {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return 'Sin datos anteriores.';
    const data = value as Record<string, unknown>;
    const lines: string[] = [];
    const labels: Record<string, string> = {customer_name: 'Cliente', phone: 'Teléfono', email: 'Correo electrónico', service_date: 'Fecha', service_time: 'Hora', template_name: 'Menú', meal_type_name: 'Servicio', covers: 'Comensales', note: 'Nota'};
    for (const [key, label] of Object.entries(labels)) {
        const field = data[key];
        if (typeof field !== 'string' && typeof field !== 'number') continue;
        let text = String(field);
        if (key === 'service_date' && /^\d{4}-\d{2}-\d{2}$/.test(text)) text = text.split('-').reverse().join('/');
        if (key === 'service_time') text = text.slice(0, 5);
        lines.push(`${label}: ${text || 'Sin indicar'}`);
    }
    if (typeof data.state === 'string') lines.push(`Estado: ${reservationStateLabel(data.state)}`);
    if (typeof data.template_day === 'number' && Number.isSafeInteger(data.template_day)) lines.push(`Día del menú: ${data.template_day + 1}`);
    const snapshot = data.menu_snapshot;
    if (typeof snapshot === 'object' && snapshot !== null && 'dishes' in snapshot && Array.isArray(snapshot.dishes)) {
        for (const candidate of snapshot.dishes as unknown[]) {
            if (typeof candidate !== 'object' || candidate === null || Array.isArray(candidate)) continue;
            const dish = candidate as Record<string, unknown>;
            if (typeof dish.recipe_name === 'string') lines.push(`Plato: ${typeof dish.course_name === 'string' && dish.course_name ? dish.course_name + ': ' : ''}${dish.recipe_name}`);
        }
    }
    return lines.length ? lines.join('\n') : 'Sin datos anteriores.';
}
export function reservationHistoryDate(value: string): string {
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('es-ES', {dateStyle: 'short', timeStyle: 'short'}).format(date) : 'Fecha desconocida';
}
