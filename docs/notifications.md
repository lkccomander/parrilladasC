# Confirmación y notificaciones

Cuando una interacción pasa a `submitted`, el API conserva la confirmación y
crea una notificación por destinatario en el mismo outbox durable que usa
WhatsApp. Cada fila tiene una clave derivada de la interacción, por lo que un
webhook repetido no duplica mensajes. El worker entrega WhatsApp mediante Meta
y correo mediante SMTP Gmail; los estados quedan en `messages` para auditoría.

Configura en el servicio `api` de Railway (como variables selladas):

```text
NOTIFICATION_WHATSAPP_NUMBERS=+50687200700,+50683383928
NOTIFICATION_EMAIL_RECIPIENTS=info@parrillasensucasa.com
NOTIFICATIONS_EMAIL_HOST=smtp.gmail.com
NOTIFICATIONS_EMAIL_PORT=587
NOTIFICATIONS_EMAIL_USERNAME=mclkcteam@gmail.com
NOTIFICATIONS_EMAIL_PASSWORD=<Gmail app password>
NOTIFICATIONS_EMAIL_FROM=mclkcteam@gmail.com
```

`NOTIFICATION_WHATSAPP_NUMBERS` y `NOTIFICATION_EMAIL_RECIPIENTS` son listas
separadas por comas. Para una prueba temporal se puede añadir
`andresch@gmail.com` a la lista de correo, confirmar una solicitud y retirar el
destinatario después. No se deben guardar contraseñas ni datos de clientes en
el repositorio.

Si SMTP no está configurado, la confirmación del cliente se conserva y el
mensaje de notificación queda en estado de entrega fallida/incierta; el fallo
no pausa la conversación del cliente.
