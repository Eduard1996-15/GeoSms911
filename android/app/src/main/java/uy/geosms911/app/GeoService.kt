package uy.geosms911.app

import android.Manifest
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.os.Looper
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.coroutines.resume

/**
 * Servicio en primer plano: mantiene la ubicación, el latido y la escucha de
 * órdenes del tutor (long-poll) mientras el teléfono está protegido.
 */
class GeoService : Service() {

    companion object {
        const val ACTION_START = "uy.geosms911.app.action.START"
        const val ACTION_STOP = "uy.geosms911.app.action.STOP"
        const val ACTION_SEND_NOW = "uy.geosms911.app.action.SEND_NOW"
        const val ACTION_COMMAND = "uy.geosms911.app.action.COMMAND"
        const val ACTION_STOP_ALARM = "uy.geosms911.app.action.STOP_ALARM"

        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_COMMAND_KIND = "command_kind"

        fun start(context: Context) {
            val intent = Intent(context, GeoService::class.java).setAction(ACTION_START)
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }

        fun sendNow(context: Context) {
            val intent = Intent(context, GeoService::class.java).setAction(ACTION_SEND_NOW)
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }

        fun stop(context: Context) {
            runCatching { context.startService(Intent(context, GeoService::class.java).setAction(ACTION_STOP)) }
        }

        fun stopAlarm(context: Context) {
            val intent = Intent(context, GeoService::class.java).setAction(ACTION_STOP_ALARM)
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }

        fun command(context: Context, commandId: String, kind: String) {
            val intent = Intent(context, GeoService::class.java)
                .setAction(ACTION_COMMAND)
                .putExtra(EXTRA_COMMAND_ID, commandId)
                .putExtra(EXTRA_COMMAND_KIND, kind)
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var api: Api
    private var locationListener: LocationListener? = null
    private var pollJob: Job? = null
    private var heartbeatJob: Job? = null
    private var running = false
    private var lastSentAt = 0L
    private var lastLocation: Location? = null

    override fun onCreate() {
        super.onCreate()
        api = Api(this)
        Notifications.ensureChannels(this)

        val notification = Notifications.serviceNotification(this, "Iniciando protección…")
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(
                    Notifications.SERVICE_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
                )
            } else {
                startForeground(Notifications.SERVICE_ID, notification)
            }
        } catch (error: Exception) {
            // Sin permiso de ubicación el sistema puede rechazar el servicio.
            Notifications.postStatus(
                this,
                "No se pudo iniciar la protección",
                "Abre GeoSms911 y concede los permisos de ubicación.",
            )
            stopSelf()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!Prefs.isPaired(this)) {
            stopSelf()
            return START_NOT_STICKY
        }

        when (intent?.action) {
            ACTION_STOP -> {
                stopEverything()
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_STOP_ALARM -> {
                AlarmPlayer.stop()
                AlarmPlayer.cancelVibration(this)
                Notifications.cancelAlert(this)
            }
            ACTION_SEND_NOW -> scope.launch { sendLocationNow(null) }
            ACTION_COMMAND -> {
                val id = intent.getStringExtra(EXTRA_COMMAND_ID).orEmpty()
                val kind = intent.getStringExtra(EXTRA_COMMAND_KIND).orEmpty()
                if (id.isNotBlank() && kind.isNotBlank()) {
                    scope.launch { executeCommand(id, kind) }
                }
            }
            else -> Unit
        }

        startLoops()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startLoops() {
        if (running) return
        running = true

        startLocationUpdates()

        pollJob = scope.launch {
            while (isActive) {
                try {
                    val commands = api.commands(20)
                    for (index in 0 until commands.length()) {
                        val command = commands.getJSONObject(index)
                        executeCommand(
                            command.optString("id"),
                            command.optString("kind"),
                        )
                    }
                } catch (error: CancellationException) {
                    throw error
                } catch (error: Exception) {
                    if (api.isRevokedError(error)) {
                        Notifications.postStatus(
                            this@GeoService,
                            "Teléfono desvinculado",
                            "Este teléfono ya no está autorizado. Pide un código nuevo a tu tutor.",
                        )
                        stopEverything()
                        stopSelf()
                        return@launch
                    }
                    delay(6_000)
                }
            }
        }

        heartbeatJob = scope.launch {
            while (isActive) {
                api.heartbeat(batteryLevel(), Prefs.sharing(this@GeoService))
                delay(60_000)
            }
        }
    }

    private fun startLocationUpdates() {
        if (!hasLocationPermission()) {
            Notifications.updateServiceNotification(
                this,
                "Falta el permiso de ubicación para protegerte.",
            )
            return
        }

        val manager = getSystemService(LocationManager::class.java) ?: return
        val listener = object : LocationListener {
            override fun onLocationChanged(location: Location) {
                lastLocation = location
                Prefs.saveFix(this@GeoService, location.latitude, location.longitude)
                val now = System.currentTimeMillis()
                if (Prefs.sharing(this@GeoService) && now - lastSentAt > 45_000) {
                    scope.launch { sendLocationNow(location) }
                }
            }

            override fun onProviderEnabled(provider: String) = Unit

            override fun onProviderDisabled(provider: String) = Unit

            @Deprecated("Requerido por la interfaz")
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
        }
        locationListener = listener

        try {
            if (manager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                manager.requestLocationUpdates(
                    LocationManager.GPS_PROVIDER,
                    30_000L,
                    20f,
                    listener,
                    Looper.getMainLooper(),
                )
            }
            if (manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                manager.requestLocationUpdates(
                    LocationManager.NETWORK_PROVIDER,
                    60_000L,
                    40f,
                    listener,
                    Looper.getMainLooper(),
                )
            }
            manager.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.let { lastLocation = it }
            Notifications.updateServiceNotification(this, "Protección activa · compartiendo ubicación")
        } catch (error: SecurityException) {
            Notifications.updateServiceNotification(this, "Falta el permiso de ubicación.")
        }
    }

    private suspend fun sendLocationNow(location: Location?): JSONObject? {
        val fix = location ?: currentLocation() ?: return null
        val battery = batteryLevel()
        val accuracy = if (fix.hasAccuracy()) fix.accuracy.toDouble() else null
        val sent = api.sendLocation(
            fix.latitude,
            fix.longitude,
            accuracy,
            battery,
            "service",
        )
        if (!sent) return null

        lastSentAt = System.currentTimeMillis()
        val time = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        Notifications.updateServiceNotification(
            this,
            "Protección activa · última ubicación $time",
        )

        return JSONObject()
            .put("lat", fix.latitude)
            .put("lng", fix.longitude)
            .put("battery", battery)
            .apply { if (accuracy != null) put("accuracy", accuracy) }
    }

    private suspend fun executeCommand(commandId: String, kind: String) {
        var result: JSONObject? = null
        var failure: String? = null

        try {
            when (kind) {
                "locate" -> {
                    result = sendLocationNow(null)
                    if (result == null) failure = "Sin ubicación disponible en el teléfono"
                }
                "ring" -> {
                    AlarmPlayer.start(this)
                    Notifications.postAlert(
                        this,
                        "Alarma activada",
                        "Tu tutor activó la alarma de este teléfono desde GeoSms911.",
                        false,
                    )
                }
                "stop_ring" -> {
                    AlarmPlayer.stop()
                    AlarmPlayer.cancelVibration(this)
                    Notifications.cancelAlert(this)
                }
                "alert_screen" -> showEmergencyScreen(
                    "Tu familia te está buscando",
                    "Tu tutor envió un aviso desde el panel. Si necesitas ayuda, llama al ${Prefs.emergencyNumber(this)}.",
                )
                "call_parent" -> showEmergencyScreen(
                    "Tu familia quiere hablar contigo",
                    "Abre GeoSms911 y usa el botón de llamada para comunicarte.",
                )
                "sync" -> {
                    result = sendLocationNow(null)
                    api.heartbeat(batteryLevel(), Prefs.sharing(this))
                }
                else -> Unit
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            failure = error.message
        } finally {
            api.ack(
                commandId,
                if (failure == null) "acked" else "failed",
                result,
                failure,
            )
        }
    }

    private fun showEmergencyScreen(title: String, message: String) {
        Notifications.postAlert(this, title, message, fullScreen = true)
        val intent = Intent(this, AlertActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(AlertActivity.EXTRA_TITLE, title)
            putExtra(AlertActivity.EXTRA_MESSAGE, message)
        }
        runCatching { startActivity(intent) }
    }

    private suspend fun currentLocation(): Location? {
        lastLocation?.let { return it }
        Prefs.lastFix(this)?.let { (lat, lng, _) ->
            return Location("cache").apply {
                latitude = lat
                longitude = lng
            }
        }
        if (!hasLocationPermission()) return null

        return withTimeoutOrNull(12_000) {
            suspendCancellableCoroutine<Location?> { continuation ->
                val manager = getSystemService(LocationManager::class.java)
                if (manager == null) {
                    continuation.resume(null)
                    return@suspendCancellableCoroutine
                }
                val provider = when {
                    manager.isProviderEnabled(LocationManager.GPS_PROVIDER) ->
                        LocationManager.GPS_PROVIDER
                    manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) ->
                        LocationManager.NETWORK_PROVIDER
                    else -> null
                }
                if (provider == null) {
                    continuation.resume(null)
                    return@suspendCancellableCoroutine
                }

                val listener = object : LocationListener {
                    override fun onLocationChanged(location: Location) {
                        if (continuation.isActive) continuation.resume(location)
                    }

                    override fun onProviderEnabled(provider: String) = Unit

                    override fun onProviderDisabled(provider: String) = Unit

                    @Deprecated("Requerido por la interfaz")
                    override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
                }

                try {
                    manager.requestSingleUpdate(provider, listener, Looper.getMainLooper())
                } catch (error: SecurityException) {
                    continuation.resume(null)
                    return@suspendCancellableCoroutine
                }

                continuation.invokeOnCancellation { manager.removeUpdates(listener) }
            }
        }
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    private fun batteryLevel(): Int {
        val manager = getSystemService(BatteryManager::class.java) ?: return 0
        return manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY).coerceIn(0, 100)
    }

    private fun stopEverything() {
        running = false
        pollJob?.cancel()
        heartbeatJob?.cancel()
        locationListener?.let { listener ->
            runCatching {
                getSystemService(LocationManager::class.java)?.removeUpdates(listener)
            }
        }
        locationListener = null
        AlarmPlayer.stop()
        AlarmPlayer.cancelVibration(this)
        scope.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    override fun onDestroy() {
        running = false
        pollJob?.cancel()
        heartbeatJob?.cancel()
        locationListener?.let { listener ->
            runCatching {
                getSystemService(LocationManager::class.java)?.removeUpdates(listener)
            }
        }
        scope.cancel()
        super.onDestroy()
    }
}
