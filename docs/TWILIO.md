# Configurar Twilio

## Estado actual de la cuenta

| Dato | Valor |
| --- | --- |
| Cuenta | `AC6671de…` (My First Twilio Account) |
| Tipo | **Trial** |
| Saldo | **0.00 USD** |
| Números | **Ninguno** |
| Números locales de Uruguay | **No disponibles** en Twilio |
| Números de Argentina | Disponibles, pero **sin SMS** (solo voz) |
| Números de EE. UU. | Disponibles con **SMS + voz** |

Con este estado el backend funciona en **modo registro**: guarda cada SMS en el
panel y en la base, pero no lo envía. La app y el dashboard funcionan igual.

## Limitación nueva de las cuentas Trial (error 572006)

Twilio restringió los Trial: **solo aceptan plantillas de SMS predefinidas**. Al
intentar enviar texto libre, la API responde:

```
572006: Unable to create record: Invalid template name.
Trial accounts can only use predefined SMS templates.
```

Las alertas de GeoSms911 necesitan texto dinámico (nombre, batería, enlace de
mapa), así que **no encajan en una plantilla**. La solución es actualizar la
cuenta a pago (Billing → agregar método de pago). Los "100 SMS gratis" del panel
solo aplican a esas plantillas de prueba, no a mensajes personalizados.

Mientras tanto todo lo demás funciona: ubicación en vivo, alertas en el panel,
órdenes por long-poll, alarma y pantalla de emergencia. Solo falta el SMS real.

## 1. Pasar a cuenta de pago

Las cuentas Trial:

- solo envían plantillas predefinidas (error 572006 con texto libre);
- solo envían a números **verificados** en la consola;
- agregan un prefijo de prueba a cada mensaje;
- no pueden comprar números sin saldo.

En <https://console.twilio.com> → **Billing** agrega un método de pago y saldo
(con USD 20 alcanza para meses de uso familiar). Al actualizar desaparecen la
plantilla obligatoria y el prefijo de prueba.

## 2. Comprar un número

Como Twilio no ofrece números uruguayos, la opción práctica es un número de
**EE. UU.** con capacidad SMS y voz (aproximadamente USD 1,15/mes + consumo).

1. Consola → **Phone Numbers → Buy a number**.
2. Filtrar por país **United States**, marcar **SMS** y **Voice**.
3. Comprar y copiar el número en formato E.164: `+1XXXXXXXXXX`.

Alternativa: si solo te interesa el puente telefónico y no los SMS, un número
argentino sirve para voz.

Luego edita `.env`:

```env
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
```

Reinicia el backend. `GET /api/health` debe mostrar `"twilio_configured": true`.

Verifica el envío desde el panel con **SMS → Enviar prueba**. El mensaje debe
llegar a tu teléfono (en Trial, primero verifica tu número en
**Phone Numbers → Verified Caller IDs**).

## 3. Exponer el backend

Twilio necesita una URL pública con HTTPS para los webhooks. Dos opciones:

### ngrok (pruebas)

```powershell
ngrok http 8000
```

Copia la URL `https://xxxx.ngrok-free.app` y colócala en `.env`:

```env
PUBLIC_BASE_URL=https://xxxx.ngrok-free.app
```

Reinicia el backend. **La URL de ngrok cambia cada vez que lo reinicias**: actualiza
`.env` y los webhooks de Twilio.

### Dominio propio (producción)

- Un VPS con Caddy o Nginx + Certbot.
- `PUBLIC_BASE_URL=https://geosms.tudominio.com`.
- El backend escuchando en `127.0.0.1:8000` detrás del proxy.

## 4. Configurar los webhooks

Consola → **Phone Numbers → Manage → Active numbers → tu número**:

| Campo | URL |
| --- | --- |
| **A message comes in** | `https://TU-URL/webhooks/twilio/sms` (método **POST**) |
| **Call comes in** | `https://TU-URL/webhooks/twilio/voice` (método **POST**) |
| **Status callback URL** (mensajes) | `https://TU-URL/webhooks/twilio/sms/status` (POST) |

`TWILIO_VALIDATE_SIGNATURE=true` exige que `PUBLIC_BASE_URL` coincida **exactamente**
con la URL que Twilio llama. Si ves `403 Firma de Twilio invalida`:

- revisa que no sobre ni falte la barra final;
- que el puerto y el esquema (`https`) sean los correctos;
- que no haya un proxy que reescriba el path.

Nunca desactives la validación en producción salvo para una prueba local puntual.

## 5. Probar

### SMS entrante

Desde tu teléfono (el registrado en el perfil del tutor) envía `DONDE` al número
de Twilio. Deberías recibir *"Buscando la ubicación de …"* y ver la orden en el
panel (pestaña Alertas/SMS).

### Puente telefónico

Llama al número de Twilio desde tu teléfono: el backend conecta con el teléfono
del menor sin revelar el número real.

O desde el panel: **Llamar** → Twilio llama a ambos y los une en una conferencia.

### Respaldo por SMS al menor

Si el teléfono lleva más de 90 s sin consultar órdenes
(`SMS_FALLBACK_AFTER_SECONDS`), la orden se envía también al número del menor:

```
GEOSMS911 A1B2C3D4 CMD 9f3a2b1c locate
```

La app valida la clave (`sms_secret`) y ejecuta la orden. Si el teléfono no tiene
saldo o el número no está configurado, no hay respaldo: por eso conviene cargar
el número del menor en el panel.

## 6. Costos aproximados

| Concepto | Costo |
| --- | --- |
| Número de EE. UU. | ~USD 1,15 / mes |
| SMS a Uruguay | depende del país; Consultar **Pricing → Messaging** en la consola |
| Llamada de voz | por minuto, según tarifa a Uruguay |
| Webhooks y backend | sin costo en Twilio |

Para una familia, el consumo típico son centavos por mes. El puente telefónico es
lo más caro: cada llamada paga minutos en ambos extremos.

## 7. Seguridad

- Rota el **Auth Token** que se compartió por chat: Consola → **Account → API keys
  & tokens → Rotate**. Actualiza `.env` y reinicia.
- No subas `.env` a git (ya está en `.gitignore`).
- Usa un número de Twilio distinto para pruebas y producción si vas a escalar.
- Revisa los logs del backend ante comandos que no reconoces.
