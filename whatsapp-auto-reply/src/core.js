'use strict';

/**
 * Lógica pura del auto-respondedor. No depende de WhatsApp ni del sistema de
 * archivos, para que se pueda probar de forma aislada.
 *
 * Estado por contacto:
 *   pendingSince     - timestamp (ms) del primer mensaje entrante sin respuesta, o null.
 *   lastInboundAt    - timestamp (ms) del último mensaje entrante.
 *   lastManualReplyAt- timestamp (ms) de la última respuesta escrita por el usuario.
 *   lastAutoReplyAt  - timestamp (ms) de la última respuesta automática enviada.
 */

const MS_PER_MINUTE = 60 * 1000;

const DEFAULT_SETTINGS = Object.freeze({
  replyAfterMinutes: 55,
  checkIntervalSeconds: 60,
  cooldownMinutes: 180,
  quietHours: null,
  defaultMessage:
    'Hola {name}, vi tu mensaje pero en este momento no puedo responder. Te contesto en cuanto me desocupe.',
});

function normalizePhone(raw) {
  return String(raw || '').replace(/\D/g, '');
}

function createEmptyState() {
  return { version: 1, contacts: {} };
}

function getContactState(state, key) {
  if (!state.contacts[key]) {
    state.contacts[key] = {
      pendingSince: null,
      lastInboundAt: null,
      lastManualReplyAt: null,
      lastAutoReplyAt: null,
    };
  }
  return state.contacts[key];
}

/** Un mensaje entrante del contacto. Solo el primero de la racha abre la ventana. */
function recordInbound(state, key, timestamp) {
  const c = getContactState(state, key);
  c.lastInboundAt = timestamp;
  if (c.pendingSince == null) {
    c.pendingSince = timestamp;
  }
  return c;
}

/** El usuario respondió a mano: se cierra la ventana y se reinicia el cooldown. */
function recordManualReply(state, key, timestamp) {
  const c = getContactState(state, key);
  c.pendingSince = null;
  c.lastManualReplyAt = timestamp;
  c.lastAutoReplyAt = null;
  return c;
}

/** Se envió una respuesta automática: se cierra la ventana y arranca el cooldown. */
function recordAutoReply(state, key, timestamp) {
  const c = getContactState(state, key);
  c.pendingSince = null;
  c.lastAutoReplyAt = timestamp;
  return c;
}

function parseClock(value) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(String(value || '').trim());
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

/**
 * quietHours = { start: "22:00", end: "07:00" } (hora local). Soporta rangos
 * que cruzan la medianoche. Dentro de las horas de silencio no se envía nada;
 * el pendiente se conserva y se atiende al terminar el silencio.
 */
function isInQuietHours(quietHours, now) {
  if (!quietHours) return false;
  const start = parseClock(quietHours.start);
  const end = parseClock(quietHours.end);
  if (start == null || end == null || start === end) return false;
  const date = new Date(now);
  const current = date.getHours() * 60 + date.getMinutes();
  if (start < end) {
    return current >= start && current < end;
  }
  return current >= start || current < end;
}

function resolveSettings(partial) {
  const merged = { ...DEFAULT_SETTINGS, ...(partial || {}) };
  for (const field of ['replyAfterMinutes', 'checkIntervalSeconds', 'cooldownMinutes']) {
    const value = Number(merged[field]);
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`settings.${field} debe ser un número >= 0 (recibido: ${merged[field]})`);
    }
    merged[field] = value;
  }
  if (merged.quietHours) {
    if (parseClock(merged.quietHours.start) == null || parseClock(merged.quietHours.end) == null) {
      throw new Error('settings.quietHours debe tener start y end en formato HH:MM');
    }
  }
  if (!merged.defaultMessage || !String(merged.defaultMessage).trim()) {
    throw new Error('settings.defaultMessage no puede estar vacío');
  }
  return merged;
}

function normalizeContacts(rawContacts) {
  if (!Array.isArray(rawContacts) || rawContacts.length === 0) {
    throw new Error('La configuración debe incluir al menos un contacto en "contacts"');
  }
  const seen = new Set();
  return rawContacts.map((raw, index) => {
    const phone = normalizePhone(raw.phone);
    if (phone.length < 7) {
      throw new Error(`contacts[${index}].phone inválido: "${raw.phone}"`);
    }
    if (seen.has(phone)) {
      throw new Error(`contacts[${index}].phone repetido: "${raw.phone}"`);
    }
    seen.add(phone);
    return {
      key: phone,
      phone,
      name: raw.name ? String(raw.name).trim() : phone,
      message: raw.message ? String(raw.message) : null,
      enabled: raw.enabled !== false,
    };
  });
}

function renderMessage(template, contact, minutesWaiting) {
  return String(template)
    .replace(/\{name\}/g, contact.name)
    .replace(/\{minutes\}/g, String(Math.round(minutesWaiting)));
}

/**
 * Devuelve los contactos a los que hay que responder ahora mismo, con el texto ya listo.
 */
function getDueReplies(state, contacts, settings, now) {
  if (isInQuietHours(settings.quietHours, now)) return [];
  const due = [];
  for (const contact of contacts) {
    if (!contact.enabled) continue;
    const c = state.contacts[contact.key];
    if (!c || c.pendingSince == null) continue;

    const waitingMs = now - c.pendingSince;
    if (waitingMs < settings.replyAfterMinutes * MS_PER_MINUTE) continue;

    if (
      c.lastAutoReplyAt != null &&
      now - c.lastAutoReplyAt < settings.cooldownMinutes * MS_PER_MINUTE
    ) {
      continue;
    }

    const minutesWaiting = waitingMs / MS_PER_MINUTE;
    due.push({
      contact,
      minutesWaiting,
      text: renderMessage(contact.message || settings.defaultMessage, contact, minutesWaiting),
    });
  }
  return due;
}

module.exports = {
  MS_PER_MINUTE,
  DEFAULT_SETTINGS,
  normalizePhone,
  createEmptyState,
  getContactState,
  recordInbound,
  recordManualReply,
  recordAutoReply,
  isInQuietHours,
  resolveSettings,
  normalizeContacts,
  renderMessage,
  getDueReplies,
};
