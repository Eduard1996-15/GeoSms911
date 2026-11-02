# Seguridad y legal

Una app que geolocaliza a un menor maneja **datos personales sensibles**. Antes de
usarla en serio, revisa estos puntos con calma. No es asesoramiento jurídico.

## 1. Consentimiento y ámbito familiar

- **Consentimiento del otro progenitor.** En Uruguay (y en la mayoría de los
  países), la patria potestad es compartida: geolocalizar a un hijo sin acuerdo
  del otro progenitor puede interpretarse como injerencia en su vida privada y
  usarse en un conflicto familiar. Documenta el acuerdo.
- **Consentimiento del menor.** Explícale qué hace la app, que tiene una
  notificación visible y que puede hablar contigo. La transparencia es también
  una medida de seguridad: si el menor sabe que el teléfono avisa, pedirá ayuda.
- **Proporcionalidad.** Usa la app para emergencias y seguridad, no para vigilar
  cada movimiento. El historial es de 24 h por defecto, no de meses.
- **No la uses para controlar a una pareja o a un adulto.** Sería ilícito.

## 2. El 911 nunca se marca solo

El diseño prohíbe el discado automático:

- La app solo abre el marcador (`ACTION_DIAL`) con el número listo.
- La llamada requiere que una persona pulse "Llamar".
- El backend nunca inicia llamadas a emergencias; solo el puente entre tutor y
  menor.

Discar emergencias sin una persona del otro lado genera falsas alarmas, moviliza
recursos y puede constituir una infracción. Además, un niño que ve una pantalla
de emergencia debe poder hablar con un adulto, no ser conectado a ciegas.

## 3. Qué datos se guardan

| Dato | Ubicación | Retención |
| --- | --- | --- |
| Ubicaciones | SQLite del backend | 30 días (`LOCATION_RETENTION_DAYS`) |
| Alertas | SQLite | Hasta que las borres |
| SMS enviados/recibidos | SQLite | Hasta que los borres |
| Token del dispositivo | Hash SHA-256 en el servidor; token en el teléfono | Hasta revocar |
| Contraseña | scrypt con sal, nunca en texto plano | Hasta borrar la cuenta |
| Ubicación en caché del teléfono | SharedPreferences | Último punto conocido |

No se envía nada a terceros salvo los SMS a Twilio (que incluyen el texto de la
alerta y el enlace del mapa) y los webhooks.

## 4. Medidas implementadas

- Contraseñas con `scrypt` (n=16384, r=8, p=1) y comparación en tiempo constante.
- JWT firmado con `APP_SECRET`; sesión de 7 días.
- Token de dispositivo aleatorio de 256 bits, guardado hasheado.
- Emparejamiento con código de 6 dígitos, de un solo uso, válido 10 minutos.
- Órdenes por SMS con clave por dispositivo (`sms_secret`).
- Validación de la firma `X-Twilio-Signature` y rechazo de webhooks sin configurar.
- Límites de intentos en login, registro, emparejamiento y órdenes.
- Aislamiento por tutor: un usuario no puede leer dispositivos ajenos.
- Auditoría de login, emparejamiento, órdenes y cambios de alertas.
- Revocación inmediata del dispositivo.
- Borrado de la cuenta y todos sus datos: `DELETE /api/auth/me`.
- Cabeceras `X-Frame-Options`, `nosniff`, CSP y `Referrer-Policy`.
- CORS configurable.

## 5. Riesgos que quedan (y cómo reducirlos)

| Riesgo | Mitigación |
| --- | --- |
| HTTP sin cifrar en pruebas | Usa HTTPS fuera de tu red local |
| Sin cifrado en reposo | Cifra el disco del servidor (BitLocker/LUKS) y limita el acceso |
| Sin 2FA en el panel | Usa una contraseña larga y única; el panel no está pensado para exponerse a internet sin más |
| El menor desinstala la app | No hay bloqueo; es una decisión de diseño ética. Te enterarás por la falta de datos |
| Servicio matado por el fabricante | Exención de batería + SMS de respaldo |
| SMS suplantados | Firma de Twilio + clave por dispositivo |
| Backend caído | La app sigue enviando al reconectar; los SMS quedan en el teléfono |

## 6. Google Play y distribución

Si publicas en Google Play, ten en cuenta:

- **Ubicación en segundo plano:** exige declaración, video y justificación. Una
  app familiar puede calificar, pero la revisión es estricta.
- **SMS (`RECEIVE_SMS`):** permiso restringido. Play solo lo aprueba para casos
  concretos (autenticación, banca, etc.). Es probable que rechacen una app de
  seguridad familiar que lo use. Para uso familiar, **instala el APK directamente**
  o distribúyelo con MDM.
- **Intención de pantalla completa:** desde Android 14 requiere permiso especial;
  Play revisa su uso.
- **Control parental:** declara la categoría correcta y no ocultes la app.

Para una familia, la vía simple es APK firmado + instalación manual. Si algún día
lo conviertes en producto, necesitarás asesoría legal y cumplimiento de Play.

## 7. Plan de emergencia real

La app **no reemplaza** una llamada. Un plan sensato:

1. El menor sabe que puede llamar al 911 y a un adulto de confianza.
2. El tutor revisa la app cuando recibe una alerta, pero no espera a que llegue
   el SMS para actuar.
3. Los contactos de emergencia están grabados en el teléfono.
4. Se prueba el sistema una vez al mes (alerta de prueba + ubicación).
5. Se revisa que la app siga con permisos y batería después de cada actualización
   del sistema.

## 8. Si pierdes el teléfono

1. Panel → **Desvincular** el dispositivo: el token deja de funcionar.
2. Cambia la contraseña del tutor.
3. Si usas Twilio, rota el Auth Token.
4. Revisa el historial de alertas y la última ubicación antes de revocar.

## 9. Marco normativo de referencia

- Uruguay: Ley 18.331 de Protección de Datos Personales y su reglamento.
- Argentina: Ley 25.326 de Protección de los Datos Personales.
- Unión Europea: RGPD (si aplica a residentes).
- Convención sobre los Derechos del Niño: interés superior y derecho a la privacidad.

Ante dudas concretas, consulta a un abogado de familia de tu país.
