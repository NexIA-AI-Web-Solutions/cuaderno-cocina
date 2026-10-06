type ScreenLock = Pick<WakeLockSentinel, 'released' | 'release' | 'addEventListener'>
type ScreenLockNavigator = {wakeLock?: {request(type: 'screen'): Promise<ScreenLock>}}
type ScreenLockDocument = Pick<Document, 'visibilityState' | 'addEventListener' | 'removeEventListener'>

export function createRecipeWakeLock(
    browser: ScreenLockNavigator | undefined,
    document: ScreenLockDocument | undefined,
    onError: (error: unknown) => void,
) {
    let lock: ScreenLock | undefined
    let wanted = false
    let pending: Promise<void> | undefined
    let generation = 0
    const visible = () => document?.visibilityState === 'visible'

    function report(error: unknown) {
        const name = error instanceof DOMException ? error.name : undefined
        // Permission/policy denial and unavailable APIs are normal for an optional
        // screen lock. Cancellation is expected only while hidden or leaving.
        if (name === 'NotAllowedError' || name === 'NotSupportedError'
            || (name === 'AbortError' && (!visible() || !wanted))) return
        onError(error)
    }

    async function releaseLock(current: ScreenLock | undefined) {
        if (!current || current.released) return
        try {
            await current.release()
        } catch (error) {
            report(error)
        }
    }

    function acquire(): Promise<void> {
        if (!wanted || !visible() || !browser?.wakeLock || (lock && !lock.released)) return Promise.resolve()
        if (pending) return pending
        const currentGeneration = generation
        pending = (async () => {
            // Defer execution until pending is assigned, including native sync throws.
            await Promise.resolve()
            try {
                const acquired = await browser.wakeLock!.request('screen')
                if (!wanted || !visible() || currentGeneration !== generation) {
                    await releaseLock(acquired)
                    return
                }
                lock = acquired
                acquired.addEventListener('release', () => {
                    if (lock !== acquired) return
                    lock = undefined
                    // A visible UA revocation may reflect battery/policy refusal.
                    // Retry on the next visibility transition, without a request loop.
                }, {once: true})
            } catch (error) {
                report(error)
            } finally {
                pending = undefined
            }
        })()
        return pending
    }

    function visibilityChanged() {
        if (visible()) {
            void acquire()
        } else {
            const current = lock
            lock = undefined
            void releaseLock(current)
        }
    }

    return {
        async request() {
            if (!wanted) {
                wanted = true
                document?.addEventListener('visibilitychange', visibilityChanged)
            }
            await acquire()
        },
        async release() {
            wanted = false
            generation++
            document?.removeEventListener('visibilitychange', visibilityChanged)
            const current = lock
            lock = undefined
            await releaseLock(current)
        },
    }
}
