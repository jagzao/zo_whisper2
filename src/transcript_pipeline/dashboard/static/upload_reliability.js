(() => {
    class ScreenWakeLock {
        constructor(navigatorRef, documentRef, onState = () => {}) {
            this.navigator = navigatorRef;
            this.document = documentRef;
            this.onState = onState;
            this.required = false;
            this.lock = null;
            this.pending = null;
            this.failed = false;
            this.supported = typeof navigatorRef?.wakeLock?.request === 'function';
            this.onVisibility = () => this.sync();
            this.onOrientation = () => this.sync();
            documentRef?.addEventListener('visibilitychange', this.onVisibility);
            globalThis.addEventListener?.('orientationchange', this.onOrientation);
            this.render();
        }

        setRequired(required) { this.required = !!required; return this.sync(); }

        render() {
            this.onState(!this.supported || this.failed ? 'unavailable' : this.lock ? 'awake' : 'inactive');
        }

        async sync() {
            const wanted = this.required && this.document?.visibilityState === 'visible';
            if (!wanted) {
                const lock = this.lock;
                this.lock = null;
                if (lock) await lock.release().catch(() => {});
                this.render();
                return;
            }
            if (!this.supported || this.lock || this.pending) { this.render(); return; }
            try {
                this.pending = this.navigator.wakeLock.request('screen');
                const lock = await this.pending;
                if (!this.required || this.document?.visibilityState !== 'visible') {
                    await lock.release().catch(() => {});
                    return;
                }
                this.failed = false;
                this.lock = lock;
                lock.addEventListener('release', () => {
                    if (this.lock === lock) this.lock = null;
                    this.render();
                    if (this.required && this.document?.visibilityState === 'visible') this.sync();
                });
            } catch (_) {
                this.failed = true;
            } finally {
                this.pending = null;
                this.render();
            }
        }

        dispose() {
            this.required = false;
            this.document?.removeEventListener('visibilitychange', this.onVisibility);
            globalThis.removeEventListener?.('orientationchange', this.onOrientation);
            return this.sync();
        }
    }

    function adaptiveUploadLimit(items, { deviceMemory = 8, backendHealthy = true, recentFailures = 0,
        pendingBytes = 0, active = 0, max = 6 } = {}) {
        const pending = items.filter(item => ['QUEUED', 'UPLOADING', 'RETRYING'].includes(item.state));
        if (!pending.length) return Math.max(1, active);
        const largest = Math.max(...pending.map(item => Number(item.size || item.file?.size || 0)));
        let limit = largest >= 2 * 1024 ** 3 || pendingBytes >= 8 * 1024 ** 3 ? 2
            : largest >= 256 * 1024 ** 2 ? (pendingBytes >= 512 * 1024 ** 2 ? 4 : 2) : 4;
        if (deviceMemory <= 4) limit = Math.min(limit, 2);
        if (!backendHealthy || recentFailures >= 2) limit = Math.min(limit, 2);
        return Math.min(max, Math.max(1, active, limit));
    }

    async function readResponseJson(response, upload = false) {
        const contentType = response.headers?.get?.('content-type') || '';
        if (!/(?:^|\/)json(?:\s*;|$)|\+json(?:\s*;|$)/i.test(contentType)) {
            const reason = response.statusText || 'Unknown Error';
            const error = new Error(`${upload ? 'Upload failed: ' : ''}HTTP ${response.status} ${reason}`);
            error.status = response.status;
            throw error;
        }
        return response.json();
    }

    async function fetchUploadWithRetry(url, options = {}, { attempts = 5, fetcher = globalThis.fetch,
        sleep = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
        for (let attempt = 0; attempt < attempts; attempt++) {
            try {
                const response = await fetcher(url, options);
                if (response.status < 500 || attempt === attempts - 1) return response;
            } catch (error) {
                if (error.name === 'AbortError' || attempt === attempts - 1) throw error;
            }
            await sleep(Math.min(8000, 500 * (2 ** attempt)));
        }
        throw new Error('Upload request failed after retries');
    }


    function suppressReselection(item) {
        return ['UPLOADING', 'RETRYING', 'FINALIZING', 'COMPLETED'].includes(item?.state);
    }

    function shouldResetUploadPump(batchStarted, activeCount, activeItems, preflightPending) {
        return !!batchStarted && activeCount === 0 && !preflightPending &&
            !activeItems.some(item => ['UPLOADING', 'RETRYING', 'FINALIZING'].includes(item.state));
    }

    async function fetchUploadWithTimeout(url, options = {}, { timeoutMs = 90000, fetcher = globalThis.fetch,
        setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
        const controller = new AbortController();
        const parent = options.signal;
        const abortFromParent = () => controller.abort(parent.reason);
        if (parent?.aborted) abortFromParent();
        else parent?.addEventListener('abort', abortFromParent, { once: true });
        let timedOut = false;
        const timer = setTimer(() => { timedOut = true; controller.abort(); }, timeoutMs);
        try {
            return await fetcher(url, { ...options, signal: controller.signal });
        } catch (error) {
            if (timedOut) { const timeout = new Error(`No response for ${Math.round(timeoutMs / 1000)}s`); timeout.code = 'UPLOAD_TIMEOUT'; throw timeout; }
            throw error;
        } finally {
            clearTimer(timer);
            parent?.removeEventListener('abort', abortFromParent);
        }
    }

    globalThis.whisperSuppressUploadReselection = suppressReselection;
    globalThis.whisperShouldResetUploadPump = shouldResetUploadPump;
    globalThis.WhisperScreenWakeLock = ScreenWakeLock;
    globalThis.whisperAdaptiveUploadLimit = adaptiveUploadLimit;
    globalThis.whisperReadDashboardJson = response => readResponseJson(response);
    globalThis.whisperReadUploadJson = response => readResponseJson(response, true);
    globalThis.whisperFetchUploadWithRetry = (url, options, config) => fetchUploadWithRetry(url, options, config);
    globalThis.whisperFetchUploadWithTimeout = (url, options, config) => fetchUploadWithTimeout(url, options, config);
    if (typeof module !== 'undefined') module.exports = { ScreenWakeLock, adaptiveUploadLimit, readResponseJson, fetchUploadWithRetry, fetchUploadWithTimeout, suppressReselection, shouldResetUploadPump };
})();
