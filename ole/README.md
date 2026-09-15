# Olé Restaurante — sitio web

Rediseño del sitio de **Olé Restaurante** (Lomas de Cocoyoc, Morelos), tomando como
base el sitio actual hecho en Canva y modernizando el formato sin perder la esencia
española ni el carácter taurino del nombre.

```
ole/
└── index.html     # el sitio completo, en un solo archivo
```

## Cómo verlo y cómo publicarlo

Abre `ole/index.html` con doble clic. No necesita servidor, ni build, ni conexión.

Para publicarlo, sube ese único archivo a cualquier hosting estático (Netlify, Vercel,
Cloudflare Pages, GitHub Pages) y apunta ahí el dominio `olerestaurante.com`. También
puede convivir con Canva mientras se decide: es un archivo independiente.

## Reglas de la casa

Las mismas que el resto del repositorio, por lo que el archivo es autocontenido:

- Sin CDN, sin fuentes remotas, sin librerías y sin analítica. Cero peticiones externas.
- Sin cookies ni rastreo. Los formularios no envían nada a terceros: abren el correo
  del visitante con el mensaje ya redactado.
- Gráficos hechos a mano en SVG, incrustados en el HTML.
- Texto de cara al cliente en español.

## Qué se rediseñó

| Del sitio actual | En el nuevo sitio |
| --- | --- |
| Página larga de bloques sueltos | Recorrido con navegación fija, siete secciones y anclas |
| Carta como imagen de pizarrón | Carta en HTML con pestañas, buscable, legible en móvil y accesible |
| Solo un botón "Contáctanos" a Instagram | Sección de redes, muro de contenido y alta al Club Olé |
| Sin formulario de reserva | Formulario de reserva con validación y armado de correo o WhatsApp |
| Horario y ubicación como texto | Horario con el día de hoy resaltado e indicador de abierto/cerrado en vivo |
| Testimonios de plantilla en inglés | Los tres testimonios reales del sitio actual |

Carácter taurino, sin caer en el cliché: silueta de toro bravo como marca y como
fondo del hero, rojo capote y oro de la marca, mosaico andaluz apenas insinuado,
grano de albero y un separador en forma de vuelo de capote.

## Configuración

Todo lo editable vive en el objeto `OLE`, en la última etiqueta `<script>` del archivo:

```js
const OLE = {
  email:      "hola@olerestaurante.com",
  telefono:   "",   // visible, p. ej. "735 000 0000"
  whatsapp:   "",   // solo dígitos con lada de país, p. ej. "527350000000"
  instagram:  "https://www.instagram.com/ole.restaurante",
  facebook:   "",   // URL completa de la página
  tiktok:     "",   // URL completa del perfil
  maps:       "https://www.google.com/maps/search/?api=1&query=...",
  abre: 14, cierra: 21, diasAbiertos: [3,4,5,6,0]   // 0 = domingo
};
```

Lo que dejes vacío **se oculta solo**: no quedan botones muertos ni enlaces rotos.
En cuanto pongas el WhatsApp aparecen el botón de la barra del hero, el de alta al
Club y el de enviar la reserva por WhatsApp.

## Qué debes reemplazar

Busca cada `data-edit` dentro del archivo.

| Marca | Qué falta | Por qué |
| --- | --- | --- |
| `telefono` | Teléfono y WhatsApp | El sitio actual no publica ninguno |
| `redes` | Facebook y TikTok | El sitio viejo listaba "Facebook" y "Twitter" como texto, sin enlace |
| `muro` | URL de cada publicación | Hoy las seis tarjetas llevan al perfil de Instagram |
| `mapa` | Dirección exacta y enlace de Google Maps | El sitio actual solo dice "Centro Comercial, Lomas de Cocoyoc" |
| `foto` | Fotografías reales | Hay siete marcadores ilustrados en SVG en su lugar |
| `logo` | Logotipo oficial | La marca del encabezado es una interpretación del logo, no el archivo original |
| `carta` | Dos renglones de la pizarra | Ver abajo |

### Fotografías

Es el cambio que más va a levantar el sitio. Los marcadores están en `.marco-foto`,
`.plato__img` y `.post svg.arte`. Sustituye cada `<svg>` por un `<img src="..." alt="...">`
y quedará igual de encuadrado, porque el contenedor ya fija la proporción.

### Dudas de transcripción de la carta

La carta se transcribió desde la imagen del pizarrón del diseño de Canva. Dos renglones
no se leen con claridad y conviene cotejarlos contra la carta impresa:

1. **"Tartar de fuet bellotero" ($240).** En la imagen se alcanza a leer algo como
   "luel"; se interpretó como *fuet*, por la descripción que lo acompaña.
2. **Un digestivo de $140** entre el pacharán y el orujo. No se descifra el nombre,
   así que **no se incluyó** en lugar de inventarlo.

También conviene confirmar "Fruta con mineral" ($70), en la sección sin alcohol.

Todo lo demás (platillos, descripciones y precios) sale tal cual del pizarrón vigente.

## De dónde salió el contenido

Del diseño **"Ole Restaurante (Website)"** en la cuenta de Canva, que es el sitio
actual. `www.olerestaurante.com` no se pudo consultar directamente desde este entorno
porque la política de red bloquea el dominio.

Datos confirmados y usados tal cual: nombre, el lema *"De Madrid a Cocoyoc"*, la
apertura en agosto de 2025, el horario de miércoles a domingo de 2 a 9 p.m., la
ubicación en el Centro Comercial de Lomas de Cocoyoc, el correo
`hola@olerestaurante.com`, el Instagram `@ole.restaurante`, los tres platillos
destacados, los tres testimonios y la carta completa con precios.

## Si algún día quieres el feed real de Instagram

El muro de redes son tarjetas enlazadas, a propósito: el `embed` oficial de Instagram
exige cargar un script de Meta, lo que rompería la regla de "sin CDN" y metería rastreo
de terceros en el sitio. Si se decide aceptarlo, se cambia el bloque `.muro` por el
`blockquote` que Instagram entrega y se añade su script. Queda a criterio del cliente.

## Aviso

Los precios están en pesos mexicanos y se indican como sujetos a cambio. Antes de
publicar, confirma que la carta del sitio coincida con la del restaurante.
