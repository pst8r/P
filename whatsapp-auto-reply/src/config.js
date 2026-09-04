'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { resolveSettings, normalizeContacts } = require('./core');

function loadDotEnv(rootDir) {
  const envPath = path.join(rootDir, '.env');
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

function loadConfig(rootDir) {
  loadDotEnv(rootDir);

  const configPath = path.resolve(rootDir, process.env.WA_CONFIG_PATH || 'config/contacts.json');
  if (!fs.existsSync(configPath)) {
    throw new Error(
      `No existe el archivo de configuración ${configPath}. ` +
        'Copia config/contacts.example.json a config/contacts.json y edítalo.'
    );
  }

  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (err) {
    throw new Error(`No se pudo leer ${configPath}: ${err.message}`);
  }

  const settings = resolveSettings(raw.settings);
  const contacts = normalizeContacts(raw.contacts);
  const dataDir = path.resolve(rootDir, process.env.WA_DATA_DIR || 'data');
  fs.mkdirSync(dataDir, { recursive: true });

  return {
    configPath,
    settings,
    contacts,
    dataDir,
    statePath: path.join(dataDir, 'state.json'),
    authDir: path.join(dataDir, 'session'),
    headless: String(process.env.WA_HEADLESS || 'true').toLowerCase() !== 'false',
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
    logLevel: (process.env.WA_LOG_LEVEL || 'info').toLowerCase(),
  };
}

module.exports = { loadConfig };
