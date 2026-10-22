const test = require('node:test');
const assert = require('node:assert/strict');
const { ScreenWakeLock, adaptiveUploadLimit } = require('../../src/transcript_pipeline/dashboard/static/upload_reliability.js');

class FakeDocument {
    visibilityState = 'visible';
    listeners = new Map();
    addEventListener(name, fn) { this.listeners.set(name, fn); }
    removeEventListener(name) { this.listeners.delete(name); }
    dispatch(name) { this.listeners.get(name)?.(); }
}

function fakeLock() {
    const listeners = new Map();
    return { released: false, addEventListener: (name, fn) => listeners.set(name, fn),
        release: async function () { this.released = true; listeners.get('release')?.(); } };
}

test('wake lock acquires, releases when hidden, and reacquires when visible', async () => {
    const document = new FakeDocument();
    const locks = [];
    const controller = new ScreenWakeLock({ wakeLock: { request: async kind => {
        assert.equal(kind, 'screen'); const lock = fakeLock(); locks.push(lock); return lock;
    } } }, document);
    await controller.setRequired(true);
    assert.equal(locks.length, 1);
    assert.equal(controller.lock, locks[0]);
    controller.onOrientation();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(locks.length, 1);
    document.visibilityState = 'hidden'; document.dispatch('visibilitychange');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(locks[0].released, true);
    document.visibilityState = 'visible'; document.dispatch('visibilitychange');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(locks.length, 2);
    await controller.setRequired(false);
    assert.equal(locks[1].released, true);
});

test('wake lock release by the platform reacquires while workflow remains active', async () => {
    const document = new FakeDocument();
    const locks = [];
    const controller = new ScreenWakeLock({ wakeLock: { request: async () => { const lock = fakeLock(); locks.push(lock); return lock; } } }, document);
    await controller.setRequired(true);
    locks[0].release();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(locks.length, 2);
    await controller.dispose();
});

test('unsupported Wake Lock reports unavailable without issuing a request', async () => {
    const states = [];
    const controller = new ScreenWakeLock({}, new FakeDocument(), state => states.push(state));
    await controller.setRequired(true);
    assert.deepEqual(states, ['unavailable', 'unavailable']);
});

test('Wake Lock request rejection reports unavailable', async () => {
    const states = [];
    const controller = new ScreenWakeLock({ wakeLock: { request: async () => { throw new Error('denied'); } } }, new FakeDocument(), state => states.push(state));
    await controller.setRequired(true);
    assert.equal(states.at(-1), 'unavailable');
});

test('adaptive concurrency respects file size, resources, failures and max six', () => {
    const file = (size, state = 'QUEUED') => ({ size, state });
    assert.equal(adaptiveUploadLimit([file(10)], {}), 4);
    assert.equal(adaptiveUploadLimit([file(600 * 1024 ** 2)], { pendingBytes: 600 * 1024 ** 2 }), 4);
    assert.equal(adaptiveUploadLimit([file(3 * 1024 ** 3)], {}), 2);
    assert.equal(adaptiveUploadLimit([file(10)], { deviceMemory: 2 }), 2);
    assert.equal(adaptiveUploadLimit([file(10)], { backendHealthy: false }), 2);
    assert.equal(adaptiveUploadLimit([file(10)], { active: 7, max: 6 }), 6);
});

test('HTML upload errors report HTTP status without parsing JSON', async () => {
    let parsed = false;
    const response = { status: 404, statusText: 'NOT FOUND', headers: { get: () => 'text/html; charset=utf-8' },
        json: async () => { parsed = true; throw new Error('Unexpected token <'); } };
    await assert.rejects(require('../../src/transcript_pipeline/dashboard/static/upload_reliability.js').readResponseJson(response, true),
        error => error.message === 'Upload failed: HTTP 404 NOT FOUND' && error.status === 404);
    assert.equal(parsed, false);
});

test('upload JSON parser accepts JSON and preserves retryable HTTP status', async () => {
    const { readResponseJson } = require('../../src/transcript_pipeline/dashboard/static/upload_reliability.js');
    const ok = { status: 200, headers: { get: () => 'application/json' }, json: async () => ({ ok: true }) };
    assert.deepEqual(await readResponseJson(ok, true), { ok: true });
    const badGateway = { status: 502, statusText: 'BAD GATEWAY', headers: { get: () => 'text/html' }, json: async () => ({}) };
    await assert.rejects(readResponseJson(badGateway, true), error => error.status === 502 && error.message === 'Upload failed: HTTP 502 BAD GATEWAY');
});
