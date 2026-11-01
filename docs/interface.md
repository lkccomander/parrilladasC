# Interfaz del panel y páginas públicas

La referencia de diseño aportada en `proyect_brain/privacy.md` se aplica a la pantalla de login, al estilo compartido del panel y a las páginas públicas `/privacy` y `/terms-of-service`.

## Referencias visuales

- [Login de referencia](https://welcome-nicaragua-bot-welcometnic.up.railway.app/login): tarjeta centrada, fondo fotográfico y campos de acceso.
- [Referencia tipográfica y de estilo](https://isaiprofitable.com/): fondo oscuro, bordes discretos, titulares condensados y etiquetas monoespaciadas.
- [Privacidad de referencia](https://welcome-nicaragua-bot-welcometnic.up.railway.app/privacy) y [términos de referencia](https://welcome-nicaragua-bot-welcometnic.up.railway.app/terms-of-service): estructura temática adaptada al negocio de parrilladas, sin copiar la identidad, contactos ni condiciones de tours.

El logo y la fotografía de comida proceden de los assets locales de Parrillas en su Casa. No se incorporan imágenes de terceros. Los archivos publicados se encuentran en `modules/dashboard/static/images`.

## Tipografía y mantenimiento

- Bebas Neue: títulos.
- Archivo variable: texto y formularios.
- IBM Plex Mono: etiquetas y metadatos.

Las fuentes se sirven localmente; no hay solicitudes a Google Fonts o CDNs durante el uso del panel. `static/fonts/sources.json` registra los paquetes Fontsource y versiones originales. Cada familia incluye su licencia SIL OFL 1.1. La política de contenido permite fuentes solo del propio origen.

Los tokens de color, tipografía y superficies están en `static/dashboard.css`. Las reglas de login y páginas legales están delimitadas dentro de ese archivo. `base.html` comparte identidad, navegación, pie legal y enlace para saltar al contenido; `login.html` adapta el marco al acceso centrado. No se modifica la lógica de autenticación para cambiar el diseño.

## Texto legal y datos comerciales

Las páginas son públicas y no consultan la base de datos. El contacto confirmado por el usuario es `info@parrillasensucasa.com`, centralizado en `legal_contact.html` para ambas páginas.

El contenido describe WhatsApp, los datos del evento, el acceso del equipo y los proveedores actuales. No se añade un consentimiento implícito por visitar el sitio, una autorización de marketing por consultar, precios, anticipos ni condiciones de cancelación no confirmadas. Las condiciones del evento se coordinan con el equipo.

La identidad jurídica/domicilio del responsable y los plazos concretos de conservación no se han proporcionado. Deben completarse y revisarse junto con las condiciones comerciales antes del lanzamiento con datos de clientes; el texto no constituye una certificación de cumplimiento legal. Como referencia de revisión se consultaron la [Ley 8968, texto oficial](https://pgrweb.go.cr/DOCS/NORMAS/1/VIGENTE/L/2010-2019/2010-2014/2011/1153F/DCEF7.HTML) y las [preguntas frecuentes de PRODHAB](https://www.prodhab.go.cr/preguntasfrecuentes.aspx).

Las páginas no activan el webhook de WhatsApp ni habilitan funcionalidades comerciales pendientes.
