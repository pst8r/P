'use strict';

const path = require('node:path');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');

const { loadConfig } = require('./config');
const { StateStore } = require('./state-store');
const { createLogger } = require('./logger');
const core = require('./core');

// Tipos de mensaje que no cuentan como "conversación" (notificaciones del sistema, llamadas, etc.).
const IGNORED_TYPES = new Set([
  'e2e_notification',
  'notification',
  'notification_template',
  'gp2',
  'call_log',
  'ciphertext',
  'protocol',
  'revoked',
]);

const rootDir = path.resolve(__dirname, '..');
const config = loadConfig(rootDir);
const log = createLogger(config.logLevel);
const store = new StateStore(config.statePath);
store.load();

const contactsByChatId = new Map(); // chatId -> contact
const chatIdByKey = new Map(); // contact.key -> chatId
const autoSentIds = new Set(); // ids de mensajes enviados por el bot
const sendingTo = new Set(); // chatIds con un envío automático en curso

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: config.authDir }),
  puppeteer: {
    headless: config.headless,
    executablePath: config.executablePath,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  },
});

function toMs(seconds) {
  return seconds * 1000;
}

async function resolveChatId(contact) {
  try {
    const numberId = await client.getNumberId(contact.phone);
    if (numberId && numberId._serialized) return numberId._serialized;
  } catch (err) {
    log.warn(`No se pudo resolver el número de ${contact.name} (${contact.phone}): ${err.message}`);
  }
  return `${contact.phone}@c.us`;
}

/**
 * Al arrancar, revisa el historial reciente de cada contacto para reconstruir
 * qué mensajes quedaron sin responder (por ejemplo, mientras el bot estaba apagado).
 */
async function reconcileFromHistory(contact, chatId) {
  let chat;
  try {
    chat = await client.getChatById(chatId);
  } catch {
    log.debug(`Sin chat previo con ${contact.name}; se empieza sin pendientes.`);
    return;
  }

  let messages;
  try {
    messages = await chat.fetchMessages({ limit: 50 });
  } catch (err) {
    log.warn(`No se pudo leer el historial de ${contact.name}: ${err.message}`);
    return;
  }

  // Recorremos del más reciente al más antiguo: lo pendiente son los mensajes
  // entrantes posteriores a nuestro último mensaje.
  let firstUnanswered = null;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (IGNORED_TYPES.has(msg.type)) continue;
    if (msg.fromMe) break;
    firstUnanswered = msg;
  }

  if (firstUnanswered) {
    const ts = toMs(firstUnanswered.timestamp);
    core.recordInbound(store.state, contact.key, ts);
    log.info(`${contact.name}: mensaje sin responder desde ${new Date(ts).toLocaleString()}`);
  } else {
    const c = core.getContactState(store.state, contact.key);
    c.pendingSince = null;
  }
}

async function sendAutoReply({ contact, text, minutesWaiting }) {
  const chatId = chatIdByKey.get(contact.key);
  if (!chatId) return;
  sendingTo.add(chatId);
  try {
    const sent = await client.sendMessage(chatId, text);
    if (sent && sent.id && sent.id._serialized) autoSentIds.add(sent.id._serialized);
    core.recordAutoReply(store.state, contact.key, Date.now());
    store.save();
    log.info(`Respuesta automática enviada a ${contact.name} (${Math.round(minutesWaiting)} min sin respuesta).`);
  } catch (err) {
    log.error(`Falló el envío a ${contact.name}: ${err.message}`);
  } finally {
    sendingTo.delete(chatId);
  }
}

async function tick() {
  const due = core.getDueReplies(store.state, config.contacts, config.settings, Date.now());
  for (const item of due) {
    await sendAutoReply(item);
  }
}

client.on('qr', (qr) => {
  log.info('Escanea este código QR con WhatsApp > Dispositivos vinculados:');
  qrcode.generate(qr, { small: true });
});

client.on('authenticated', () => log.info('Sesión autenticada.'));
client.on('auth_failure', (msg) => log.error(`Fallo de autenticación: ${msg}`));
client.on('disconnected', (reason) => log.warn(`Desconectado de WhatsApp: ${reason}`));

client.on('ready', async () => {
  log.info('Cliente listo. Resolviendo contactos...');
  for (const contact of config.contacts) {
    const chatId = await resolveChatId(contact);
    contactsByChatId.set(chatId, contact);
    chatIdByKey.set(contact.key, chatId);
    log.debug(`${contact.name} -> ${chatId}`);
    await reconcileFromHistory(contact, chatId);
  }
  store.save();

  const s = config.settings;
  log.info(
    `Vigilando ${config.contacts.length} contacto(s). ` +
      `Se responde tras ${s.replyAfterMinutes} min sin contestar; revisión cada ${s.checkIntervalSeconds} s.`
  );
  await tick();
  setInterval(() => tick().catch((err) => log.error(`Error en la revisión periódica: ${err.message}`)),
    toMs(s.checkIntervalSeconds));
});

// message_create se emite tanto para mensajes entrantes como para los que enviamos nosotros.
client.on('message_create', (msg) => {
  if (IGNORED_TYPES.has(msg.type) || msg.isStatus) return;
  const chatId = msg.fromMe ? msg.to : msg.from;
  const contact = contactsByChatId.get(chatId);
  if (!contact) return;

  const ts = toMs(msg.timestamp) || Date.now();
  if (msg.fromMe) {
    const isAuto = autoSentIds.delete(msg.id && msg.id._serialized) || sendingTo.has(chatId);
    if (isAuto) return;
    core.recordManualReply(store.state, contact.key, ts);
    log.info(`Respondiste a ${contact.name}; se cancela el pendiente.`);
  } else {
    const before = store.state.contacts[contact.key] && store.state.contacts[contact.key].pendingSince;
    core.recordInbound(store.state, contact.key, ts);
    if (before == null) log.info(`Nuevo mensaje de ${contact.name}; empieza a contar el tiempo.`);
  }
  store.save();
});

async function shutdown(signal) {
  log.info(`Recibido ${signal}; cerrando...`);
  try {
    store.save();
    await client.destroy();
  } finally {
    process.exit(0);
  }
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

client.initialize().catch((err) => {
  log.error(`No se pudo iniciar el cliente: ${err.message}`);
  process.exit(1);
});
