# App Android

## Requisitos

- Android 8.0 (API 26) o superior.
- Teléfono con GPS y Google Play Services no es obligatorio (usa `LocationManager`).
- Android Studio (para compilar) o el wrapper incluido + JDK 17.

## Compilar el APK

```powershell
cd android
.\gradlew.bat assembleDebug
```

Salida:

```
android\app\build\outputs\apk\debug\app-debug.apk
```

Para una versión de distribución:

```powershell
.\gradlew.bat assembleRelease
```

El release sin firma no se puede instalar: crea un keystore y configura
`signingConfigs` antes de distribuirlo.

## Instalar

```powershell
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
```

O copia el APK al teléfono y ábrelo (requiere permitir "Instalar apps
desconocidas" para el explorador de archivos).

## Conectar con el backend

1. En el panel web: **+ Emparejar** → aparece un código de 6 dígitos.
2. En la app: escribe la URL del servidor.
   - Emulador Android: `http://10.0.2.2:8000`
   - Teléfono en la misma Wi-Fi: `http://192.168.x.x:8000` (IP de tu PC)
   - Internet: `https://tu-dominio` (siempre HTTPS)
3. Escribe el código, el nombre del teléfono y, opcionalmente, su número.
4. **Emparejar**.

La app guarda un `device_token` propio. Puedes revocarlo desde el panel
(**Desvincular**) o desde el teléfono.

## Permisos: por qué cada uno

| Permiso | Para qué |
| --- | --- |
| Ubicación precisa | Enviar coordenadas útiles |
| Ubicación en segundo plano | Seguir funcionando con la pantalla apagada |
| SMS | Recibir órdenes de respaldo cuando no hay datos |
| Notificaciones | Mostrar la alerta y el estado del servicio |
| Servicio en primer plano | Mantener el GPS y la escucha activos |
| Ignorar ahorro de batería | Evitar que el fabricante cierre la app |

En Android 11+ la ubicación "todo el tiempo" se concede aparte: la app abre los
ajustes del sistema. En Android 14+ el permiso de SMS es de tipo "restringido",
pero se puede conceder manualmente al instalar por fuera de Play Store.

## Qué hace la app

- **SOS:** mantener 3 segundos → alerta + ubicación + batería.
- **Servicio en primer plano:** GPS cada 30 s, latido cada 60 s y long-poll de
  órdenes cada ~20 s.
- **Órdenes:** localizar, timbre, silenciar, pantalla de emergencia, sincronizar.
- **SMS:** si el backend no lo alcanza, envía
  `GEOSMS911 <clave> CMD <id> <orden>`; la app valida la clave.
- **Reinicio:** vuelve a arrancar tras apagar o actualizar el teléfono.
- **911:** solo abre el marcador (`ACTION_DIAL`). Nunca llama sola.

## Batería y fabricantes

Los teléfonos Xiaomi, Samsung, Huawei, Oppo y Vivo suelen matar servicios en
segundo plano. Medidas que ya implementa la app:

- servicio en primer plano con notificación permanente;
- exención de optimización de batería (botón en la app);
- reinicio automático al arrancar;
- respaldo por SMS aunque el servicio esté caído.

Además, en los ajustes del fabricante conviene:

- Xiaomi: Autostart + "Sin restricciones" de batería.
- Samsung: quitar la app de "Apps en suspensión".
- Huawei: "Ejecutar en segundo plano" manual.

## Privacidad y bloqueo

- La app no tiene pantalla de administración remota: solo ejecuta las órdenes
  definidas.
- No se puede desinstalar silenciosamente; el menor puede desvincular el
  teléfono, y el tutor recibe la novedad en el panel (dispositivo revocado).
- Si el teléfono se pierde, revoca el dispositivo desde el panel: el token deja
  de funcionar de inmediato.

## Limitaciones

- Sin FCM: si el fabricante mata el servicio, las órdenes esperan al próximo
  arranque o al SMS de respaldo.
- Sin cifrado de extremo a extremo: usa HTTPS y un backend propio.
- No funciona apagado, sin batería o sin cobertura (salvo el último punto
  conocido).
