/** Keep failed requests retryable even after editing another payload. */
export function inventoryRequests() {
    const pending = new Map<string, string>()
    function key(operation: string, payload: unknown) {
        const fingerprint = JSON.stringify([operation, payload])
        if (!pending.has(fingerprint)) pending.set(fingerprint, crypto.randomUUID())
        return pending.get(fingerprint)!
    }
    return {
        key,
        complete(operation: string, payload: unknown) {
            pending.delete(JSON.stringify([operation, payload]))
        },
        override(operation: string, payload: unknown) {
            const requestKey = key(operation, payload)
            return async ({init}: {init: RequestInit}) => {
                const headers = new Headers(init.headers)
                headers.set('Idempotency-Key', requestKey)
                return {...init, headers}
            }
        },
    }
}

export type ReceiptDraftIdentity = {order: number; entry: number; quantity: string}

export function sameReceiptDraft(
    order: number | null,
    entry: number | null,
    quantity: string,
    submitted: ReceiptDraftIdentity,
): boolean {
    return order === submitted.order && entry === submitted.entry && quantity === submitted.quantity
}
