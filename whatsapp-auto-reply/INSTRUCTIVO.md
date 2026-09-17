# Instructivo de puesta en marcha

Guía paso a paso para dejar corriendo el auto-respondedor de WhatsApp. Sigue los pasos en orden;
cada uno indica cómo comprobar que quedó bien antes de pasar al siguiente.

Tiempo estimado la primera vez: **15 a 20 minutos**.

---

## Paso 0. Lo que necesitas antes de empezar

| Requisito | Detalle | Cómo lo compruebas |
| --- | --- | --- |
| Node.js 18 o superior | Recomendado 20 o 22 (LTS). Se descarga de <https://nodejs.org> | `node --version` |
| npm | Viene incluido con Node.js | `npm --version` |
| Teléfono con WhatsApp | El mismo número que va a responder | — |
| Una computadora encendida | El proceso debe estar corriendo para que las respuestas salgan a tiempo | — |
| Conexión a internet | Sin bloqueos hacia `web.whatsapp.com` | Abre <https://web.whatsapp.com> en tu navegador |
| ~400 MB libres en disco | Dependencias más Chromium | — |

> **Importante sobre el teléfono.** La app se vincula como "dispositivo vinculado", igual que
> WhatsApp Web. Tu teléfono **no** necesita estar conectado permanentemente, pero sí debe
> conectarse a internet al menos una vez cada 14 días o WhatsApp cierra la sesión vinculada.

---

## Paso 1. Obtener el código

Si aún no tienes el repositorio en tu computadora:

```bash
git clone https://github.com/pst8r/P.git
cd P
git checkout claude/whatsapp-auto-replies-e4xrrm
cd whatsapp-auto-reply
```

Si ya lo tienes, solo colócate en la carpeta:

```bash
cd ruta/a/P/whatsapp-auto-reply
```

**Comprobación:** `ls` debe mostrar `package.json`, `src/`, `config/` y `test/`.

---

## Paso 2. Instalar dependencias

```bash
npm install
```

Esto instala `whatsapp-web.js` y, con él, **puppeteer**, que descarga su propio Chromium
(unos 150 MB). Es normal que este paso tarde unos minutos la primera vez.

**Comprobación:** al terminar debe existir la carpeta `node_modules/` y no debe haber errores
en rojo (los avisos `npm warn deprecated` son inofensivos).

### Si ya tienes Chrome o Chromium instalado

Para no descargar otro navegador, dile a la app cuál usar. Crea el archivo `.env` (ver Paso 4)
con la ruta correspondiente:

| Sistema | Ruta habitual |
| --- | --- |
| macOS | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` |
| Windows | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| Linux (Debian/Ubuntu) | `/usr/bin/google-chrome` o `/usr/bin/chromium` |

En ese caso puedes instalar sin descargar el navegador:

```bash
PUPPETEER_SKIP_DOWNLOAD=1 npm install
```

### Si estás en un servidor Linux sin escritorio

Chromium necesita algunas librerías del sistema. En Debian/Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y \
  libnss3 libatk-bridge2.0-0 libgbm1 libasound2 libgtk-3-0 libxshmfence1 libxss1
```

---

## Paso 3. Configurar tus contactos

Copia la plantilla y edítala:

```bash
cp config/contacts.example.json config/contacts.json
```

Abre `config/contacts.json` con cualquier editor de texto y déjalo así (con tus datos reales):

```json
{
  "settings": {
    "replyAfterMinutes": 55,
    "checkIntervalSeconds": 60,
    "cooldownMinutes": 180,
    "quietHours": { "start": "23:00", "end": "07:00" },
    "defaultMessage": "Hola {name}, vi tu mensaje pero ahorita no puedo responder bien. Te contesto en cuanto me desocupe."
  },
  "contacts": [
    {
      "name": "María",
      "phone": "+52 55 1234 5678",
      "message": "Hola María, ando en juntas. Te respondo hoy mismo, ¿va?"
    },
    { "name": "Cliente ACME", "phone": "+1 415 555 0100" },
    { "name": "Proveedor pausado", "phone": "+52 33 1111 2222", "enabled": false }
  ]
}
```

### Qué significa cada ajuste

| Ajuste | Para qué sirve | Valor sugerido |
| --- | --- | --- |
| `replyAfterMinutes` | Minutos que puede esperar un mensaje sin respuesta tuya antes de que la app conteste | `55` (así nadie pasa de 1 hora) |
| `checkIntervalSeconds` | Cada cuánto revisa si hay pendientes | `60` |
| `cooldownMinutes` | Tiempo mínimo entre dos respuestas automáticas al mismo contacto, para no ser repetitivo | `180` |
| `quietHours` | Franja local en la que no se envía nada. Usa `null` para desactivarla | `{"start":"23:00","end":"07:00"}` |
| `defaultMessage` | Texto para los contactos que no traen mensaje propio | Tu texto |

### Qué significa cada campo de un contacto

| Campo | Obligatorio | Notas |
| --- | --- | --- |
| `phone` | Sí | **Con código de país.** Se aceptan espacios, guiones, `+` y paréntesis |
| `name` | No | Se usa en los mensajes y en el log. Si falta, se muestra el número |
| `message` | No | Texto solo para ese contacto. Si falta, se usa `defaultMessage` |
| `enabled` | No | Ponlo en `false` para pausar a alguien sin borrarlo |

### Comodines en los mensajes

- `{name}` se reemplaza por el nombre del contacto.
- `{minutes}` se reemplaza por los minutos que lleva esperando.

Ejemplo: `"Hola {name}, perdón por la demora de {minutes} minutos."`

### Detalle importante sobre el número

Debe ser el número **tal como está en WhatsApp**, con código de país y sin el `1` extra que en
México a veces se escribe después del `+52`. Para verificarlo, abre el chat de esa persona en
WhatsApp Web y revisa el número que aparece en el encabezado.

**Comprobación:** el Paso 5 te dirá si el archivo tiene algún error.

---

## Paso 4. Variables de entorno (opcional)

Solo si necesitas cambiar rutas o depurar:

```bash
cp .env.example .env
```

| Variable | Para qué | Por defecto |
| --- | --- | --- |
| `WA_CONFIG_PATH` | Ruta del archivo de contactos | `config/contacts.json` |
| `WA_DATA_DIR` | Carpeta de sesión y estado | `data` |
| `PUPPETEER_EXECUTABLE_PATH` | Usar un Chrome/Chromium ya instalado | el de puppeteer |
| `WA_HEADLESS` | `false` abre el navegador visible, útil para depurar | `true` |
| `WA_LOG_LEVEL` | `debug`, `info`, `warn` o `error` | `info` |

Si no creas el `.env`, la app funciona igual con los valores por defecto.

---

## Paso 5. Chequeo previo

Antes de conectarte a WhatsApp, verifica que todo esté en su lugar:

```bash
npm run doctor
```

Salida esperada:

```
Chequeo del entorno — whatsapp-auto-reply

  ✔ Versión de Node.js: Node 22.22.2
  ✔ Dependencias instaladas: 1.34.7
  ✔ Archivo de configuración: 2 contacto(s); responde tras 55 min; enfriamiento 180 min; horas de silencio: 23:00–07:00
  ✔ Contactos: María <+525512345678>, Cliente ACME <+14155550100>
  ✔ Navegador (Chrome/Chromium): /usr/bin/chromium
  ✔ El navegador ejecuta: Chromium 141.0.7390.37
  ! Sesión de WhatsApp: Aún no hay sesión vinculada. En el primer "npm start" tendrás que escanear el código QR.

Listo para "npm start", con 1 aviso(s) que conviene revisar.
```

El aviso de la sesión es normal la primera vez. Si aparece alguna línea con `✖`, resuélvela antes
de continuar: el propio mensaje indica el comando o el archivo que hay que corregir.

Este chequeo **no** se conecta a WhatsApp ni envía ningún mensaje.

---

## Paso 6. Primer arranque y vinculación con el teléfono

```bash
npm start
```

En la terminal aparecerá un código QR, así:

```
[2026-09-17T04:10:22.104Z] INFO Escanea este código QR con WhatsApp > Dispositivos vinculados:
█████████████████████████████
██ ▄▄▄▄▄ █▀ █▀▀██ ▄▄▄▄▄ ████
...
```

En tu teléfono:

1. Abre **WhatsApp**.
2. Android: menú **⋮** > **Dispositivos vinculados**.
   iPhone: **Configuración** > **Dispositivos vinculados**.
3. Toca **Vincular un dispositivo** y desbloquea con tu huella o código.
4. Apunta la cámara al código QR de la terminal.

> Si el QR se ve deformado, agranda la ventana de la terminal o reduce el tamaño de letra
> (`Ctrl` + `-`) hasta que se vea cuadrado y completo.

Con la vinculación lista verás algo como:

```
[...] INFO Sesión autenticada.
[...] INFO Cliente listo. Resolviendo contactos...
[...] INFO María: mensaje sin responder desde 17/9/2026, 3:42:10
[...] INFO Vigilando 2 contacto(s). Se responde tras 55 min sin contestar; revisión cada 60 s.
```

A partir de ahí la app está trabajando. **Deja esa terminal abierta.**

La sesión queda guardada en `data/session/`, así que los siguientes arranques ya no piden el QR.

---

## Paso 7. Probar que realmente responde

No esperes 55 minutos para saber si funciona. Haz una prueba corta:

1. Detén la app con `Ctrl` + `C`.
2. En `config/contacts.json` pon temporalmente:
   - `"replyAfterMinutes": 2`
   - `"quietHours": null`
   - deja **un solo** contacto, de alguien de confianza que te pueda ayudar a probar.
3. Arranca de nuevo con `npm start`.
4. Pídele a esa persona que te escriba y **no le respondas**.
5. A los ~2 minutos verás en la terminal:
   `INFO Respuesta automática enviada a María (2 min sin respuesta).`
   y esa persona recibirá el mensaje.
6. Vuelve a poner `"replyAfterMinutes": 55`, restaura tus horas de silencio y tus contactos, y
   reinicia.

También conviene probar el caso contrario: que te escriban, que **tú respondas** dentro de los
2 minutos, y confirmar que la app **no** manda nada. En la terminal verás
`INFO Respondiste a María; se cancela el pendiente.`

---

## Paso 8. Qué esperar en la operación diaria

Mensajes que verás en el log y qué significan:

| Mensaje | Significa |
| --- | --- |
| `Nuevo mensaje de X; empieza a contar el tiempo.` | Llegó un mensaje y arrancó el cronómetro |
| `Respondiste a X; se cancela el pendiente.` | Contestaste tú; no se enviará nada automático |
| `Respuesta automática enviada a X (57 min sin respuesta).` | Se envió el mensaje configurado |
| `X: mensaje sin responder desde ...` | Al arrancar, detectó un pendiente previo |
| `Desconectado de WhatsApp: ...` | Se perdió la vinculación; revisa el Paso 12 |

Comportamiento que conviene tener claro:

- Solo se atienden los números de la lista. Los grupos y cualquier otro contacto se ignoran por completo.
- El cronómetro arranca con el **primer** mensaje sin responder de la racha, no con el último.
- Si respondes desde cualquier dispositivo (teléfono, WhatsApp Web, escritorio), la app lo detecta
  y cancela el pendiente.
- Durante las horas de silencio no se envía nada, pero el pendiente no se pierde: se atiende al terminar la franja.
- El estado vive en `data/state.json`. Si borras esa carpeta, se pierden los pendientes en curso, no la sesión.

---

## Paso 9. Dejarlo corriendo de forma permanente

Cerrar la terminal detiene la app. Para que siga trabajando, elige una opción.

> **Antes que nada:** configura tu computadora para que **no se suspenda**. Una laptop cerrada
> detiene el proceso y no se envía nada. Para uso 24/7 lo ideal es un servidor pequeño (VPS),
> una Raspberry Pi o una computadora que quede siempre encendida.

### Opción A. pm2 (la más sencilla, sirve en Windows, macOS y Linux)

```bash
npm install -g pm2
cd ruta/a/P/whatsapp-auto-reply
pm2 start npm --name whatsapp-auto-reply -- start
pm2 logs whatsapp-auto-reply     # ver el log en vivo (Ctrl+C solo cierra el log)
pm2 save                         # recordar el proceso
pm2 startup                      # imprime un comando para arrancar al encender; ejecútalo
```

Comandos útiles: `pm2 restart whatsapp-auto-reply`, `pm2 stop whatsapp-auto-reply`,
`pm2 status`.

> La primera vinculación con QR conviene hacerla con `npm start` (Paso 6). Con la sesión ya
> guardada, pm2 arranca sin pedir nada.

### Opción B. systemd (servidor Linux)

Crea `/etc/systemd/system/whatsapp-auto-reply.service`:

```ini
[Unit]
Description=WhatsApp Auto-Reply
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=TU_USUARIO
WorkingDirectory=/ruta/a/P/whatsapp-auto-reply
ExecStart=/usr/bin/node src/index.js
Restart=always
RestartSec=10
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
```

Luego:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now whatsapp-auto-reply
sudo systemctl status whatsapp-auto-reply
journalctl -u whatsapp-auto-reply -f     # ver el log en vivo
```

### Opción C. Dejar la terminal abierta

Válido para probar unos días. En Linux o macOS puedes usar `screen` o `tmux` para que sobreviva
al cierre de la ventana:

```bash
tmux new -s whatsapp
npm start
# Ctrl+B y luego D para salir dejándolo corriendo
tmux attach -t whatsapp   # para volver a verlo
```

---

## Paso 10. Cambiar contactos o mensajes

1. Edita `config/contacts.json`.
2. Reinicia: `Ctrl` + `C` y `npm start`, o `pm2 restart whatsapp-auto-reply`,
   o `sudo systemctl restart whatsapp-auto-reply`.

La configuración se lee al arrancar, así que **los cambios no aplican hasta reiniciar**.
Reiniciar no borra la sesión ni los pendientes.

---

## Paso 11. Detener o desvincular

| Quiero... | Cómo |
| --- | --- |
| Detener temporalmente | `Ctrl` + `C`, o `pm2 stop whatsapp-auto-reply` |
| Pausar a un contacto | Ponle `"enabled": false` y reinicia |
| Olvidar la sesión y volver a escanear el QR | Detén la app y borra la carpeta `data/session/` |
| Empezar de cero (sesión y pendientes) | Detén la app y borra toda la carpeta `data/` |
| Quitar el acceso desde el teléfono | WhatsApp > **Dispositivos vinculados** > selecciona el dispositivo > **Cerrar sesión** |

---

## Paso 12. Solución de problemas

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `Error de configuración: No existe el archivo...` | Falta `config/contacts.json` | `cp config/contacts.example.json config/contacts.json` |
| `contacts[0].phone inválido` | El número tiene menos de 7 dígitos o está vacío | Escríbelo con código de país |
| `contacts[1].phone repetido` | El mismo número aparece dos veces | Deja una sola entrada |
| `net::ERR_TUNNEL_CONNECTION_FAILED` o `ERR_NAME_NOT_RESOLVED` | Sin internet, o un proxy/VPN bloquea WhatsApp | Verifica la conexión; permite `web.whatsapp.com` en el proxy corporativo |
| `Failed to launch the browser process` | Falta el navegador | `npx puppeteer browsers install chrome`, o define `PUPPETEER_EXECUTABLE_PATH` |
| `error while loading shared libraries: libnss3.so` | Faltan librerías del sistema en Linux | Instala los paquetes del Paso 2 |
| El QR no se escanea | La terminal recorta o deforma el código | Agranda la ventana y reduce el tamaño de letra |
| `Desconectado de WhatsApp: LOGOUT` | Cerraste el dispositivo vinculado desde el teléfono | Borra `data/session/` y vuelve a vincular |
| Arranca pero nunca responde | Sigues respondiendo antes del umbral, estás en horas de silencio, o el número no coincide | Revisa el log y compara el número con el que aparece en WhatsApp Web |
| Respondió cuando no debía | El umbral es muy corto | Sube `replyAfterMinutes` |
| Responde de más al mismo contacto | El enfriamiento es muy corto | Sube `cooldownMinutes` |

Si algo no encaja en la tabla, ejecuta `npm run doctor` y, para ver más detalle en el log:

```bash
WA_LOG_LEVEL=debug npm start
```

Para ver qué está haciendo el navegador por dentro:

```bash
WA_HEADLESS=false npm start
```

---

## Paso 13. Seguridad y buenas prácticas

- **Nunca subas `data/` ni `config/contacts.json` a un repositorio.** Contienen tu sesión de
  WhatsApp y números de personas reales. Ya están en `.gitignore`; no los fuerces con `git add -f`.
- Quien tenga acceso a `data/session/` puede leer y escribir en tu WhatsApp. Trátala como una contraseña.
- Usa la app con tu cuenta personal y una lista corta de contactos. `whatsapp-web.js` automatiza
  WhatsApp Web y **no es una API oficial de Meta**: el envío masivo o automatizado a desconocidos
  puede provocar la suspensión del número.
- Para un número de negocio o volumen alto, la vía oficial es la WhatsApp Business Cloud API.
- Avisa a los contactos de la lista, o redacta el mensaje de forma que sea evidente que es una
  respuesta automática. Es lo correcto y evita malentendidos.

---

## Referencia rápida

```bash
npm install          # una sola vez
npm run doctor       # verificar el entorno
npm start            # arrancar (la primera vez pide el QR)
npm test             # pruebas de la lógica (no toca WhatsApp)
```

| Archivo | Contenido |
| --- | --- |
| `config/contacts.json` | Tus contactos y ajustes (no se sube al repo) |
| `.env` | Rutas y nivel de log (opcional, no se sube al repo) |
| `data/session/` | Sesión de WhatsApp vinculada |
| `data/state.json` | Pendientes y marcas de tiempo |
