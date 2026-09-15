# Olé Restaurante — sitio web

Rediseño del sitio de **Olé Restaurante** (Lomas de Cocoyoc, Morelos), tomando como
base el sitio actual hecho en Canva y modernizando el formato sin perder la esencia
española ni el carácter taurino del nombre.

```
ole/
├── index.html          # el sitio completo, en un solo archivo
├── assets/
│   ├── logo.png        # logotipo oficial en alta resolución (el sitio lo lleva incrustado)
│   ├── LEEME.txt
│   └── fotos/          # aquí van las fotos de @ole.restaurante
└── export/             # el sitio exportado para subirlo a Canva
    ├── ole-sitio-canva.pdf
    ├── ole-sitio-completo.png
    ├── secciones/
    └── LEEME.txt
```

## Cómo verlo y cómo publicarlo

Abre `ole/index.html` con doble clic. No necesita servidor, ni build, ni conexión.

Para publicarlo, sube la carpeta `ole/` completa a cualquier hosting estático
(Netlify, Vercel, Cloudflare Pages, GitHub Pages) y apunta ahí el dominio
`olerestaurante.com`. También puede convivir con Canva mientras se decide.

## Lo que falta para publicar

Solo las fotografías, y no requieren tocar código.

### 1. Las fotografías de @ole.restaurante

Van once fotos en `ole/assets/fotos/`, con estos nombres exactos:

| Archivo | Dónde va | Formato |
| --- | --- | --- |
| `hero.jpg` | Fondo de la portada | Horizontal, mínimo 2000 px de ancho |
| `salon.jpg` | Sección "Sobre Olé" | Vertical, 4:5 |
| `pinchos.jpg` | Platillo destacado | Horizontal, 4:3 |
| `arroz-meloso.jpg` | Platillo destacado | Horizontal, 4:3 |
| `merluza.jpg` | Platillo destacado | Horizontal, 4:3 |
| `ig-1.jpg` … `ig-6.jpg` | Muro de redes | Cuadradas, 1:1 |

Los pies de foto del muro ya están escritos y, en orden, son: arroz meloso, barra de
pinchos, tintos, jamón al corte, el salón y sidra escanciada. Si subes otras fotos,
ajusta esos pies y los enlaces de cada tarjeta en la sección `redes`.

**No fue posible descargar las fotos automáticamente.** La política de red de este
entorno bloquea `instagram.com` y su CDN, igual que bloquea `olerestaurante.com`.
Hay que bajarlas a mano desde la cuenta y comprimirlas: menos de 300 KB cada una,
menos de 600 KB la de la portada. El sitio no usa CDN, así que el peso se nota directo.

Mientras falten los archivos, cada hueco muestra el marcador ilustrado que ya trae el
sitio, así que nunca se ve roto. La consola del navegador sí reporta un 404 por cada
archivo ausente; desaparecen en cuanto los subas.

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
| Carta como imagen de pizarrón | Carta en HTML con pestañas, legible en móvil y accesible |
| Solo un botón "Contáctanos" a Instagram | Sección de redes, muro de contenido y alta al Club Olé |
| Sin formulario de reserva | Formulario de reserva con validación y armado de correo o WhatsApp |
| Horario y ubicación como texto | Horario con el día de hoy resaltado e indicador de abierto/cerrado en vivo |
| Testimonios de plantilla en inglés | Los tres testimonios reales del sitio actual |

Carácter taurino, sin caer en el cliché: silueta de toro bravo como marca de agua de
la portada, mosaico andaluz apenas insinuado y un separador en forma de vuelo de
capote. La identidad la lleva el logotipo oficial; el toro es solo textura de fondo.

## El logotipo y la paleta

El logotipo es marca registrada, así que el sitio usa el archivo oficial en el
encabezado, la portada y el pie. Lo recorté y convertí el fondo gris del original en
transparencia, de modo que se apoya sobre cualquier color sin recuadro.

Va **incrustado dentro de `index.html`**, no enlazado: el archivo se abre solo, sin
carpeta al lado, y siempre muestra la marca correcta. Antes estaba enlazado a
`assets/logo.png` y, al abrir el HTML suelto, no lo encontraba y caía a un respaldo
tipográfico provisional. Ese respaldo ya no existe. El original en alta resolución
sigue en `assets/logo.png` para cuando lo necesites aparte.

La paleta sale del propio logotipo, medida con cuentagotas:

| Color | Valor | Dónde |
| --- | --- | --- |
| Rojo Olé | `#FA001B` | Acentos, botones y antetítulos |
| Rojo hondo | `#D10018` | Bloque de testimonios y estados de hover |
| Oro Olé | `#FDB700` | Subrayados, títulos de la pizarra y filete del pie |
| Gris Olé | `#EFEFEF` | Fondo dominante del sitio, el mismo del logotipo |
| Pizarra | `#2A2624` | Solo la carta, para que funcione como pizarrón |

El sitio es claro de arriba abajo. Las letras de "RESTAURANTE" en el logotipo son
gris oscuro, así que sobre un fondo negro desaparecen: por eso el encabezado, la
portada y el pie son claros. Los únicos bloques de contraste fuerte son la carta y
los testimonios.

## La carta no lleva precios

Por decisión del cliente, la carta muestra platillos y descripciones, sin importes.
El texto de la sección remite al mesero para precios y para el fuera de carta. Los
importes están en el historial de git por si algún día se quieren recuperar.

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
En cuanto pongas el WhatsApp aparecen el botón de la barra de portada, el de alta al
Club y el de enviar la reserva por WhatsApp.

## Qué más falta por confirmar

Busca cada `data-edit` dentro del archivo.

| Marca | Qué falta | Por qué |
| --- | --- | --- |
| `telefono` | Teléfono y WhatsApp | El sitio actual no publica ninguno |
| `redes` | Facebook y TikTok | El sitio viejo listaba "Facebook" y "Twitter" como texto, sin enlace |
| `muro` | URL de cada publicación | Hoy las seis tarjetas llevan al perfil de Instagram |
| `mapa` | Dirección exacta y enlace de Google Maps | El sitio actual solo dice "Centro Comercial, Lomas de Cocoyoc" |
| `carta` | Dos renglones de la pizarra | Ver abajo |

### Dudas de transcripción de la carta

La carta se transcribió desde la imagen del pizarrón del diseño de Canva. Dos renglones
no se leen con claridad y conviene cotejarlos contra la carta impresa:

1. **"Tartar de fuet bellotero".** En la imagen se alcanza a leer algo como "luel";
   se interpretó como *fuet*, por la descripción que lo acompaña.
2. **Un digestivo** entre el pacharán y el orujo. No se descifra el nombre, así que
   **no se incluyó** en lugar de inventarlo.

También conviene confirmar "Fruta con mineral", en la sección sin alcohol.

Todo lo demás sale tal cual del pizarrón vigente.

## De dónde salió el contenido

Del diseño **"Ole Restaurante (Website)"** en la cuenta de Canva, que es el sitio
actual. `www.olerestaurante.com` no se pudo consultar directamente desde este entorno
porque la política de red bloquea el dominio.

Datos confirmados y usados tal cual: nombre, el lema *"De Madrid a Cocoyoc"*, la
apertura en agosto de 2025, el horario de miércoles a domingo de 2 a 9 p.m., la
ubicación en el Centro Comercial de Lomas de Cocoyoc, el correo
`hola@olerestaurante.com`, el Instagram `@ole.restaurante`, los tres platillos
destacados, los tres testimonios y la carta completa.

## El archivo para Canva

En `export/` está el sitio exportado para subirlo a Canva, con las instrucciones en
`export/LEEME.txt`. No se pudo crear directamente en la cuenta: la conexión con Canva
se cayó a mitad de la sesión y la red de este entorno bloquea el dominio.

Las imágenes se generaron sin las fotografías reales. Si primero dejas las fotos en
`assets/fotos/` y se vuelve a exportar, salen con las fotos puestas.

Vale la pena decirlo: `index.html` ya funciona solo y no necesita Canva. Al pasar por
Canva se pierden el formulario de reserva, el alta al Club, las pestañas de la carta
y el indicador de abierto/cerrado, porque quedan como dibujo. Canva conviene si quien
vaya a mantener el sitio prefiere editarlo ahí.

## Si algún día quieres el feed real de Instagram

El muro de redes son tarjetas enlazadas, a propósito: el `embed` oficial de Instagram
exige cargar un script de Meta, lo que rompería la regla de "sin CDN" y metería rastreo
de terceros en el sitio. Si se decide aceptarlo, se cambia el bloque `.muro` por el
`blockquote` que Instagram entrega y se añade su script. Queda a criterio del cliente.
