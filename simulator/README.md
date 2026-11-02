# Simulador

Script que emula el telefono del menor para probar GeoSms911 sin Android ni
credenciales de Twilio.

```bash
# 1. Genera un codigo desde el dashboard (boton "Emparejar")
# 2. Ejecuta:
python simulator/device_sim.py --code 123456 --panic
```

Opciones utiles:

| Opcion | Descripcion |
| --- | --- |
| `--server` | URL del backend (por defecto `http://127.0.0.1:8000`) |
| `--name` | Nombre que vera el tutor en el panel |
| `--phone` | Numero del telefono simulado, para probar el respaldo por SMS |
| `--lat` / `--lng` | Posicion inicial (por defecto Montevideo) |
| `--interval` | Segundos entre puntos de ubicacion (por defecto 15) |
| `--panic` | Envia una alerta de panico al arrancar |
| `--no-walk` | No simula movimiento |
| `--once` | Envia un solo punto y termina |
| `--reset` | Borra las credenciales guardadas en `.device.json` |

El simulador guarda sus credenciales en `simulator/.device.json` para no tener
que emparejar en cada arranque. Ese archivo no se versiona.
