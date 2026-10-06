export async function settleComponentRequest<T>(
    request: Promise<T>,
    signal: AbortSignal,
    onSuccess: (value: T) => void,
    onError: (error: unknown) => void,
): Promise<void> {
    try {
        const value = await request
        if (!signal.aborted) {
            onSuccess(value)
        }
    } catch (error) {
        if (!signal.aborted) {
            onError(error)
        }
    }
}
