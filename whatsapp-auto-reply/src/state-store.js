'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { createEmptyState } = require('./core');

/** Persistencia del estado en JSON, con escritura atómica para no corromperlo. */
class StateStore {
  constructor(filePath) {
    this.filePath = filePath;
    this.state = createEmptyState();
  }

  load() {
    if (!fs.existsSync(this.filePath)) return this.state;
    try {
      const parsed = JSON.parse(fs.readFileSync(this.filePath, 'utf8'));
      if (parsed && typeof parsed === 'object' && parsed.contacts) {
        this.state = parsed;
      }
    } catch {
      // Un archivo corrupto no debe impedir arrancar: se parte de cero.
      this.state = createEmptyState();
    }
    return this.state;
  }

  save() {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
    const tmp = `${this.filePath}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.state, null, 2));
    fs.renameSync(tmp, this.filePath);
  }
}

module.exports = { StateStore };
