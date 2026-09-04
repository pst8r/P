# WhatsApp Auto-Reply

Servicio que vigila tu WhatsApp personal y responde automáticamente a **contactos predefinidos**
cuando uno de sus mensajes lleva demasiado tiempo sin respuesta tuya (por defecto, 55 minutos,
para que nadie de la lista se quede sin contestar por más de una hora).

## Cómo funciona

1. Se vincula a tu cuenta como un dispositivo más (igual que WhatsApp Web), escaneando un QR una sola vez.
2. Por cada contacto de la lista:
   - Cuando te llega un mensaje, empieza a contar el tiempo desde el **primer** mensaje sin responder.
   - Si respondes tú a mano, el contador se cancela.
   - Si pasa el umbral (`replyAfterMinutes`) sin que respondas, el bot envía el mensaje configurado.
3. Después de una respuesta automática, no vuelve a escribirle al mismo contacto durante
   `cooldownMinutes` (a menos que respondas tú en medio, lo que reinicia todo).
4. Al arrancar, revisa el historial reciente de cada chat, así que los mensajes recibidos mientras
   el bot estaba apagado también se detectan.
5. Los mensajes de grupos y los de números fuera de la lista se ignoran por completo.

## Requisitos

- Node.js 18 o superior.
- Un teléfono con WhatsApp para escanear el QR.
- Chrome/Chromium: `whatsapp-web.js` usa puppeteer, que descarga su propio Chromium en `npm install`.
  Si prefieres usar uno ya instalado, define `PUPPETEER_EXECUTABLE_PATH` (ver `.env.example`).

## Instalación

```bash
cd whatsapp-auto-reply
npm install
cp config/contacts.example.json config/contacts.json
cp .env.example .env        # opcional
```

Edita `config/contacts.json`:

```json
{
  "settings": {
    "replyAfterMinutes": 55,
    "checkIntervalSeconds": 60,
    "cooldownMinutes": 180,
    "quietHours": { "start": "23:00", "end": "07:00" },
    "defaultMessage": "Hola {name}, vi tu mensaje pero ahora no puedo responder. Te contesto en cuanto me desocupe."
  },
  "contacts": [
    { "name": "María", "phone": "+52 55 1234 5678", "message": "Hola María, te respondo hoy mismo." },
    { "name": "Cliente ACME", "phone": "+1 415 555 0100" },
    { "name": "Pausado", "phone": "+52 33 0000 0000", "enabled": false }
  ]
}
```

| Campo | Descripción |
| --- | --- |
| `replyAfterMinutes` | Minutos sin respuesta tuya antes de enviar la automática. |
| `checkIntervalSeconds` | Cada cuánto se revisa si hay pendientes. |
| `cooldownMinutes` | Mínimo entre dos respuestas automáticas al mismo contacto. |
| `quietHours` | Rango local `HH:MM` en el que no se envía nada (o `null`). Los pendientes se atienden al terminar. |
| `defaultMessage` | Texto para contactos sin `message` propio. Admite `{name}` y `{minutes}`. |
| `contacts[].phone` | Número con código de país; se aceptan espacios, paréntesis y guiones. |
| `contacts[].message` | Texto específico para ese contacto (opcional). |
| `contacts[].enabled` | `false` para pausar un contacto sin borrarlo. |

## Uso

```bash
npm start
```

La primera vez aparece un QR en la terminal: en el teléfono ve a
**WhatsApp > Dispositivos vinculados > Vincular un dispositivo** y escanéalo.
La sesión queda guardada en `data/session/`, así que en los siguientes arranques no hace falta repetirlo.

El estado de pendientes se guarda en `data/state.json`. Para volver a empezar de cero, borra `data/`.

Para mantenerlo corriendo de forma permanente usa `pm2`, un servicio de systemd o un contenedor;
el proceso debe estar encendido para que las respuestas salgan a tiempo.

## Pruebas

La lógica de decisión (umbral, cooldown, horas de silencio, plantillas) está en `src/core.js`
y se prueba sin WhatsApp:

```bash
npm test
```

## Estructura

```
whatsapp-auto-reply/
├── src/
│   ├── index.js        # Conexión a WhatsApp, eventos y envío
│   ├── core.js         # Lógica pura: estado, umbrales, cooldown, plantillas
│   ├── config.js       # Carga y validación de config/contacts.json y .env
│   ├── state-store.js  # Persistencia atómica de data/state.json
│   └── logger.js
├── config/contacts.example.json
├── test/core.test.js
└── .env.example
```

## Advertencias

- `whatsapp-web.js` automatiza WhatsApp Web; **no es una API oficial de Meta**. Úsalo con tu cuenta
  personal bajo tu propio riesgo y evita enviar mensajes masivos. Para uso comercial a escala,
  la opción oficial es la WhatsApp Business Cloud API.
- Nunca subas `data/` ni `config/contacts.json` al repositorio: contienen tu sesión y datos personales
  (ya están en `.gitignore`).
