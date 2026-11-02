# GeoSms911

Panel familiar de **ubicación, alertas y emergencias** para Android, con respaldo
por SMS cuando el teléfono del menor no tiene datos.

El proyecto nace de una idea común pero técnicamente inviable: *"que Twilio active
el GPS y llame al 911 del teléfono de mi hijo"*. Eso no es posible: un SMS no puede
ejecutar acciones en un teléfono y Google no expone una API para manejar dispositivos
ajenos. GeoSms911 implementa la versión que **sí funciona**: una app instalada en el
teléfono del menor que obedece órdenes firmadas y un backend que coordina todo.

```
┌──────────────────────────┐        ┌──────────────────────────┐        ┌───────────────────┐
│  Teléfono del menor      │        │  Backend (FastAPI)       │        │  Panel del tutor  │
│  App Android (Kotlin)    │◀──────▶│  SQLite + WebSocket      │◀──────▶│  Mapa + alertas   │
│  · Botón SOS             │  HTTPS │  · Alertas y geocercas   │  HTTPS │  · Órdenes        │
│  · GPS en segundo plano  │        │  · Órdenes y auditoría   │        │  · Historial SMS  │
│  · Alarma / pantalla SOS │        │  · Twilio (SMS y voz)    │        │  · Zonas seguras  │
└──────────────────────────┘        └──────────────────────────┘        └───────────────────┘
              ▲                                  ▲
              └──────── SMS de respaldo ─────────┘
                 (cuando no hay datos móviles)
```

## Qué hace realmente

| Función | Cómo funciona |
| --- | --- |
| Ver ubicación en vivo | La app envía puntos GPS al backend; el panel los recibe por WebSocket |
| Botón de pánico | Se mantiene 3 s: la app envía alerta + ubicación + batería y el tutor recibe SMS |
| Activar alarma del teléfono | Orden `ring` por long-poll o SMS; suena aunque esté en silencio |
| Pantalla de emergencia | Orden `alert_screen`: pantalla completa con botón para marcar al 911 |
| Llamada tutor ↔ menor | Twilio llama a ambos y los une en una conferencia |
| Zonas seguras | Aviso cuando el teléfono sale de un radio definido |
| Comandos por SMS | `DONDE`, `TIMBRE`, `SOS`, `LLAMAR`, `ESTADO`, `OK` |
| Historial | Ubicaciones 24 h, alertas y registro de cada SMS |

## Qué no hace (a propósito)

- **No marca el 911 automáticamente.** Solo abre el marcador con el número listo
  (`ACTION_DIAL`). La llamada la confirma una persona. El software que disca
  emergencias solo genera falsas alarmas y responsabilidad legal.
- **No controla un iPhone.** iOS no permite este nivel de automatización.
- **No usa la "API de Google Assistant".** Esa API no existe públicamente para
  teléfonos de terceros. La app compañera es la única vía real.
- **No funciona con el teléfono apagado o sin batería.**

## Estructura

```
GeoSms911/
├─ backend/              API + dashboard web (FastAPI, SQLite)
│  ├─ app/
│  │  ├─ main.py         Aplicación, seguridad y estáticos
│  │  ├─ models.py       Usuarios, dispositivos, alertas, órdenes…
│  │  ├─ routers/        auth, devices, ingest, alerts, geofences, twilio…
│  │  ├─ services.py     Ubicación, alertas y geocercas
│  │  ├─ sms.py          Envío por Twilio (o registro local)
│  │  └─ voice.py        TwiML y puente telefónico
│  ├─ static/            Dashboard (Leaflet vendorizado, sin build)
│  └─ tests/             16 pruebas de extremo a extremo
├─ android/              App Kotlin (minSdk 26, target 35)
├─ simulator/            Emulador del teléfono en Python
├─ docs/                 Twilio, seguridad/legal y Android
└─ .env.example          Plantilla de configuración
```

## Arranque rápido

### 1. Backend

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
# edita .env (mínimo: APP_SECRET)
.\scripts\run.ps1
```

En Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
./scripts/run.sh
```

Abre <http://127.0.0.1:8000>, crea la cuenta del tutor y guarda tu teléfono en el
perfil (es obligatorio para recibir SMS).

### 2. Emparejar un teléfono (sin Android)

Con el simulador puedes probar todo el flujo en dos minutos:

```powershell
# 1. En el panel: botón "+ Emparejar" → copia el código de 6 dígitos
# 2. En otra terminal:
.\.venv\Scripts\python.exe simulator\device_sim.py --code 123456 --panic
```

El simulador simula movimiento, responde a las órdenes y envía alertas. Con
`--help` ves todas las opciones.

### 3. Instalar la app Android

```powershell
cd android
.\gradlew.bat assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

En el teléfono: abre la app, escribe la URL del servidor y el código de 6 dígitos.

- **Emulador:** `http://10.0.2.2:8000`
- **Teléfono en la misma red:** `http://192.168.x.x:8000`
- **Producción:** `https://tu-dominio` (usa HTTPS; el tráfico con contraseña y
  tokens no debe ir por HTTP fuera de tu red local).

La app pedirá ubicación, ubicación en segundo plano, SMS y notificaciones. Detalle
paso a paso en [docs/ANDROID.md](docs/ANDROID.md).

## Estado de Twilio

La cuenta de desarrollo está en **modo Trial con un número de prueba
proporcionado por Twilio**. Twilio restringe los Trial a **plantillas de SMS
predefinidas**: al enviar texto libre la API devuelve `572006`. Por eso los
mensajes de alerta quedan registrados en el panel con ese error pero no salen.

Todo lo demás funciona hoy: ubicación en vivo, alertas, órdenes, alarma y
pantalla de emergencia. Para activar los SMS reales hay que actualizar la cuenta
a pago y comprar un número. Pasos en [docs/TWILIO.md](docs/TWILIO.md).

## Comandos por SMS

Desde el teléfono registrado del tutor, al número de Twilio:

| Comando | Acción |
| --- | --- |
| `DONDE` | Pide ubicación al instante |
| `TIMBRE` | Activa la alarma del teléfono |
| `SILENCIO` | Detiene la alarma |
| `SOS` | Muestra la pantalla de emergencia |
| `LLAMAR` | Crea el puente telefónico con el menor |
| `ESTADO` | Batería, última conexión y ubicación |
| `OK` | Confirma las alertas abiertas |
| `AYUDA` | Lista de comandos |

Sin datos móviles, el servidor manda al menor un SMS con el formato
`GEOSMS911 <clave> CMD <id> <orden>`. La app valida la clave y ejecuta la orden.

## API

Documentación interactiva: <http://127.0.0.1:8000/api/docs>

| Grupo | Rutas |
| --- | --- |
| Autenticación | `POST /api/auth/register`, `POST /api/auth/login`, `GET/PATCH /api/auth/me` |
| Dispositivos | `POST /api/devices/pairing-code`, `POST /api/devices/register`, `GET /api/devices`, `PATCH /api/devices/{id}` |
| Órdenes | `POST /api/devices/{id}/commands`, `POST /api/devices/{id}/call`, `POST /api/devices/{id}/test-alert` |
| Ingesta (app) | `POST /api/ingest/location`, `/alert`, `/heartbeat`; `GET /api/ingest/commands?wait=20` |
| Alertas | `GET /api/alerts`, `POST /api/alerts/{id}` |
| Zonas | `GET/POST /api/geofences`, `PATCH/DELETE /api/geofences/{id}` |
| Tiempo real | `WS /ws?token=…` |
| Twilio | `POST /webhooks/twilio/sms`, `/sms/status`, `/voice`, `/voice/conference` |

## Pruebas

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
```

Cubren registro y login, emparejamiento de un solo uso, aislamiento entre tutores,
panico, geocercas, ciclo completo de órdenes, firma de Twilio y webhooks cerrados
cuando no hay configuración.

## Seguridad y legal

Antes de usar esto con un menor real, lee
[docs/SEGURIDAD-Y-LEGAL.md](docs/SEGURIDAD-Y-LEGAL.md). Puntos clave:

- Consentimiento informado del menor y del otro progenitor si corresponde.
- El 911 se marca solo con confirmación humana.
- Los tokens de dispositivo se guardan hasheados; las sesiones vencen a los 7 días.
- Los SMS de órdenes llevan una clave por dispositivo y se pueden revocar.
- Revisa la retención de ubicaciones (`LOCATION_RETENTION_DAYS`, 30 por defecto).
- Rota el token de Twilio que se compartió por chat.

## Limitaciones conocidas

- **Sin FCM:** las órdenes viajan por long-poll (el servicio debe seguir vivo) y
  por SMS como respaldo. Algunos fabricantes (Xiaomi, Samsung, Huawei) matan
  servicios en segundo plano; la app pide explícitamente quitar el ahorro de
  batería. Migrar a Firebase Cloud Messaging es la mejora natural.
- **Android solamente.**
- **El puente telefónico consume saldo de Twilio** y requiere que ambos contesten.
- **SQLite** es suficiente para una familia, no para un producto multiusuario.
- La app no bloquea ni controla el teléfono: solo comparte ubicación y recibe avisos.

## Próximos pasos sugeridos

1. Comprar el número de Twilio y configurar los webhooks.
2. Instalar la app en el teléfono real y probar 24 h con batería.
3. Añadir FCM para despertar la app sin depender del long-poll.
4. Firmar el APK con una clave propia y distribuirlo por MDM o instalación directa.
5. Si se publica en Google Play, cumplir las políticas de ubicación en segundo
   plano, SMS y control parental (ver docs/SEGURIDAD-Y-LEGAL.md).

## Licencia

Uso privado/familiar. Si lo vas a distribuir, revisa las licencias de Leaflet
(BSD-2), OpenStreetMap (ODbL) y las dependencias de Python/Kotlin.
