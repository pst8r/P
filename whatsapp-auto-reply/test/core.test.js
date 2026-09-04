'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../src/core');

const MIN = core.MS_PER_MINUTE;
const T0 = Date.UTC(2026, 0, 1, 12, 0, 0);

function setup(overrides = {}) {
  const settings = core.resolveSettings({ replyAfterMinutes: 55, cooldownMinutes: 180, ...overrides });
  const contacts = core.normalizeContacts([
    { name: 'María', phone: '+52 55 1234 5678', message: 'Hola {name}, llevas {minutes} min esperando.' },
    { name: 'ACME', phone: '+1 (415) 555-0100' },
  ]);
  const state = core.createEmptyState();
  return { settings, contacts, state, maria: contacts[0], acme: contacts[1] };
}

test('normalizePhone deja solo dígitos', () => {
  assert.equal(core.normalizePhone('+52 (55) 1234-5678'), '525512345678');
});

test('normalizeContacts rechaza teléfonos inválidos o repetidos', () => {
  assert.throws(() => core.normalizeContacts([{ phone: '123' }]), /inválido/);
  assert.throws(
    () => core.normalizeContacts([{ phone: '5255123456' }, { phone: '+52 55 12 34 56' }]),
    /repetido/
  );
  assert.throws(() => core.normalizeContacts([]), /al menos un contacto/);
});

test('resolveSettings aplica valores por defecto y valida', () => {
  const s = core.resolveSettings({});
  assert.equal(s.replyAfterMinutes, 55);
  assert.equal(s.checkIntervalSeconds, 60);
  assert.throws(() => core.resolveSettings({ replyAfterMinutes: -1 }), /replyAfterMinutes/);
  assert.throws(() => core.resolveSettings({ quietHours: { start: '25:00', end: '07:00' } }), /quietHours/);
});

test('no responde antes del umbral y sí después', () => {
  const { settings, contacts, state, maria } = setup();
  core.recordInbound(state, maria.key, T0);

  assert.deepEqual(core.getDueReplies(state, contacts, settings, T0 + 54 * MIN), []);

  const due = core.getDueReplies(state, contacts, settings, T0 + 55 * MIN);
  assert.equal(due.length, 1);
  assert.equal(due[0].contact.key, maria.key);
  assert.equal(due[0].text, 'Hola María, llevas 55 min esperando.');
});

test('usa el mensaje por defecto cuando el contacto no tiene uno propio', () => {
  const { settings, contacts, state, acme } = setup({ defaultMessage: 'Hola {name}!' });
  core.recordInbound(state, acme.key, T0);
  const due = core.getDueReplies(state, contacts, settings, T0 + 60 * MIN);
  assert.equal(due[0].text, 'Hola ACME!');
});

test('el primer mensaje de la racha fija el inicio; los siguientes no lo mueven', () => {
  const { settings, contacts, state, maria } = setup();
  core.recordInbound(state, maria.key, T0);
  core.recordInbound(state, maria.key, T0 + 30 * MIN);
  assert.equal(state.contacts[maria.key].pendingSince, T0);
  assert.equal(core.getDueReplies(state, contacts, settings, T0 + 56 * MIN).length, 1);
});

test('una respuesta manual cancela el pendiente', () => {
  const { settings, contacts, state, maria } = setup();
  core.recordInbound(state, maria.key, T0);
  core.recordManualReply(state, maria.key, T0 + 10 * MIN);
  assert.deepEqual(core.getDueReplies(state, contacts, settings, T0 + 120 * MIN), []);
});

test('tras la respuesta automática aplica el cooldown y luego vuelve a responder', () => {
  const { settings, contacts, state, maria } = setup();
  core.recordInbound(state, maria.key, T0);
  core.recordAutoReply(state, maria.key, T0 + 55 * MIN);
  assert.deepEqual(core.getDueReplies(state, contacts, settings, T0 + 56 * MIN), []);

  // El contacto vuelve a escribir 5 min después de la respuesta automática.
  core.recordInbound(state, maria.key, T0 + 60 * MIN);
  // A los 55 min de ese mensaje seguimos en cooldown (180 min desde la auto-respuesta).
  assert.deepEqual(core.getDueReplies(state, contacts, settings, T0 + 115 * MIN), []);
  // Al terminar el cooldown se responde de nuevo.
  assert.equal(core.getDueReplies(state, contacts, settings, T0 + 235 * MIN).length, 1);
});

test('una respuesta manual reinicia el cooldown', () => {
  const { settings, contacts, state, maria } = setup();
  core.recordAutoReply(state, maria.key, T0);
  core.recordManualReply(state, maria.key, T0 + 5 * MIN);
  core.recordInbound(state, maria.key, T0 + 10 * MIN);
  assert.equal(core.getDueReplies(state, contacts, settings, T0 + 70 * MIN).length, 1);
});

test('los contactos deshabilitados se ignoran', () => {
  const settings = core.resolveSettings({});
  const contacts = core.normalizeContacts([{ phone: '5255123456789', enabled: false }]);
  const state = core.createEmptyState();
  core.recordInbound(state, contacts[0].key, T0);
  assert.deepEqual(core.getDueReplies(state, contacts, settings, T0 + 90 * MIN), []);
});

test('isInQuietHours soporta rangos normales y que cruzan la medianoche', () => {
  const at = (h, m = 0) => new Date(2026, 0, 1, h, m).getTime();
  const night = { start: '22:00', end: '07:00' };
  assert.equal(core.isInQuietHours(night, at(23)), true);
  assert.equal(core.isInQuietHours(night, at(3)), true);
  assert.equal(core.isInQuietHours(night, at(7)), false);
  assert.equal(core.isInQuietHours(night, at(12)), false);

  const lunch = { start: '13:00', end: '14:00' };
  assert.equal(core.isInQuietHours(lunch, at(13, 30)), true);
  assert.equal(core.isInQuietHours(lunch, at(14)), false);
  assert.equal(core.isInQuietHours(null, at(13)), false);
});

test('en horas de silencio no se responde, pero el pendiente se conserva', () => {
  const { contacts, state, maria } = setup();
  const settings = core.resolveSettings({ replyAfterMinutes: 1, quietHours: { start: '00:00', end: '23:59' } });
  const now = new Date(2026, 0, 1, 12, 0).getTime();
  core.recordInbound(state, maria.key, now - 60 * MIN);
  assert.deepEqual(core.getDueReplies(state, contacts, settings, now), []);
  assert.equal(state.contacts[maria.key].pendingSince, now - 60 * MIN);
});
