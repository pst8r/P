#!/usr/bin/env node
'use strict';

/**
 * Chequeo previo: verifica que el entorno esté listo antes del primer arranque.
 * No se conecta a WhatsApp ni envía nada; solo revisa Node, configuración y navegador.
 * Uso: npm run doctor
 */

const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const rootDir = path.resolve(__dirname, '..');
const results = [];

function check(name, fn) {
  try {
    const detail = fn();
    results.push({ status: 'ok', name, detail: detail || '' });
  } catch (err) {
    results.push({ status: err.warning ? 'warn' : 'fail', name, detail: err.message });
  }
}

function warn(message) {
  const err = new Error(message);
  err.warning = true;
  throw err;
}

check('Versión de Node.js', () => {
  const major = Number(process.versions.node.split('.')[0]);
  if (major < 18) throw new Error(`Node ${process.versions.node}; se requiere 18 o superior.`);
  return `Node ${process.versions.node}`;
});

check('Dependencias instaladas', () => {
  if (!fs.existsSync(path.join(rootDir, 'node_modules', 'whatsapp-web.js'))) {
    throw new Error('Falta node_modules. Ejecuta: npm install');
  }
  return require(path.join(rootDir, 'node_modules', 'whatsapp-web.js', 'package.json')).version;
});

let config = null;
check('Archivo de configuración', () => {
  const { loadConfig } = require(path.join(rootDir, 'src', 'config'));
  config = loadConfig(rootDir);
  const s = config.settings;
  return (
    `${config.contacts.length} contacto(s); responde tras ${s.replyAfterMinutes} min; ` +
    `enfriamiento ${s.cooldownMinutes} min; ` +
    `horas de silencio: ${s.quietHours ? `${s.quietHours.start}–${s.quietHours.end}` : 'ninguna'}`
  );
});

check('Contactos', () => {
  if (!config) throw new Error('No se pudo leer la configuración (ver arriba).');
  const activos = config.contacts.filter((c) => c.enabled);
  if (activos.length === 0) warn('Todos los contactos tienen "enabled": false; no se responderá a nadie.');
  return activos.map((c) => `${c.name} <+${c.phone}>`).join(', ');
});

check('Navegador (Chrome/Chromium)', () => {
  const explicit = process.env.PUPPETEER_EXECUTABLE_PATH;
  if (explicit) {
    if (!fs.existsSync(explicit)) {
      throw new Error(`PUPPETEER_EXECUTABLE_PATH apunta a ${explicit}, que no existe.`);
    }
    return `${explicit} (PUPPETEER_EXECUTABLE_PATH)`;
  }
  let execPath;
  try {
    execPath = require(path.join(rootDir, 'node_modules', 'puppeteer')).executablePath();
  } catch {
    throw new Error('No se pudo consultar puppeteer. Ejecuta: npm install');
  }
  if (!fs.existsSync(execPath)) {
    throw new Error(
      `No existe el navegador en ${execPath}. Ejecuta "npx puppeteer browsers install chrome" ` +
        'o define PUPPETEER_EXECUTABLE_PATH con un Chrome/Chromium ya instalado.'
    );
  }
  return execPath;
});

check('El navegador ejecuta', () => {
  const browser = process.env.PUPPETEER_EXECUTABLE_PATH ||
    require(path.join(rootDir, 'node_modules', 'puppeteer')).executablePath();
  if (!fs.existsSync(browser)) throw new Error('Sin navegador que probar (ver arriba).');
  const version = execFileSync(browser, ['--version'], { encoding: 'utf8', timeout: 20000 }).trim();
  return version;
});

check('Sesión de WhatsApp', () => {
  const sessionDir = config ? config.authDir : path.join(rootDir, 'data', 'session');
  if (!fs.existsSync(sessionDir) || fs.readdirSync(sessionDir).length === 0) {
    warn('Aún no hay sesión vinculada. En el primer "npm start" tendrás que escanear el código QR.');
  }
  return `Sesión guardada en ${sessionDir}; no hará falta escanear el QR.`;
});

const icon = { ok: '✔', warn: '!', fail: '✖' };
console.log('\nChequeo del entorno — whatsapp-auto-reply\n');
for (const r of results) {
  console.log(`  ${icon[r.status]} ${r.name}${r.detail ? `: ${r.detail}` : ''}`);
}

const fails = results.filter((r) => r.status === 'fail').length;
const warns = results.filter((r) => r.status === 'warn').length;
console.log('');
if (fails > 0) {
  console.log(`${fails} problema(s) por resolver antes de ejecutar "npm start".\n`);
  process.exit(1);
}
console.log(
  warns > 0
    ? `Listo para "npm start", con ${warns} aviso(s) que conviene revisar.\n`
    : 'Todo en orden. Ejecuta "npm start".\n'
);
