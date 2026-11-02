package uy.geosms911.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.format.DateUtils
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var setupCard: View
    private lateinit var homeCard: View
    private lateinit var permCard: View
    private lateinit var chipStatus: TextView
    private lateinit var serverInput: TextInputEditText
    private lateinit var codeInput: TextInputEditText
    private lateinit var nameInput: TextInputEditText
    private lateinit var phoneInput: TextInputEditText
    private lateinit var pairButton: Button
    private lateinit var setupError: TextView
    private lateinit var homeTitle: TextView
    private lateinit var homeSubtitle: TextView
    private lateinit var sosButton: Button
    private lateinit var sosProgress: ProgressBar
    private lateinit var lastSyncText: TextView
    private lateinit var permStatus: TextView
    private lateinit var permButton: Button
    private lateinit var backgroundButton: Button
    private lateinit var batteryButton: Button

    private var holdJob: Job? = null

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        updatePermissionUi()
        if (Prefs.isPaired(this)) GeoService.start(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        Notifications.ensureChannels(this)
        bindViews()
        setupActions()

        if (Prefs.isPaired(this)) {
            showHome()
            GeoService.start(this)
        } else {
            showSetup()
        }
        handleDeepLink(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleDeepLink(intent)
    }

    override fun onResume() {
        super.onResume()
        updatePermissionUi()
        if (Prefs.isPaired(this)) {
            showHome()
            refreshHome()
        }
    }

    private fun bindViews() {
        setupCard = findViewById(R.id.setupCard)
        homeCard = findViewById(R.id.homeCard)
        permCard = findViewById(R.id.permCard)
        chipStatus = findViewById(R.id.chipStatus)
        serverInput = findViewById(R.id.serverInput)
        codeInput = findViewById(R.id.codeInput)
        nameInput = findViewById(R.id.nameInput)
        phoneInput = findViewById(R.id.phoneInput)
        pairButton = findViewById(R.id.pairButton)
        setupError = findViewById(R.id.setupError)
        homeTitle = findViewById(R.id.homeTitle)
        homeSubtitle = findViewById(R.id.homeSubtitle)
        sosButton = findViewById(R.id.sosButton)
        sosProgress = findViewById(R.id.sosProgress)
        lastSyncText = findViewById(R.id.lastSyncText)
        permStatus = findViewById(R.id.permStatus)
        permButton = findViewById(R.id.permButton)
        backgroundButton = findViewById(R.id.backgroundButton)
        batteryButton = findViewById(R.id.batteryButton)

        if (Prefs.serverUrl(this).isNotBlank()) {
            serverInput.setText(Prefs.serverUrl(this))
        }
        nameInput.setText("${Build.MANUFACTURER} ${Build.MODEL}")
    }

    private fun setupActions() {
        pairButton.setOnClickListener { pairDevice() }

        @Suppress("ClickableViewAccessibility")
        sosButton.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startHold()
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    cancelHold()
                    true
                }
                else -> false
            }
        }

        findViewById<Button>(R.id.shareButton).setOnClickListener {
            GeoService.sendNow(this)
            Toast.makeText(this, "Enviando tu ubicación…", Toast.LENGTH_SHORT).show()
        }

        findViewById<Button>(R.id.mapButton).setOnClickListener { openMap() }

        findViewById<Button>(R.id.stopAlarmButton).setOnClickListener {
            GeoService.stopAlarm(this)
            Toast.makeText(this, "Alarma detenida", Toast.LENGTH_SHORT).show()
        }

        permButton.setOnClickListener { permissionLauncher.launch(neededPermissions()) }
        backgroundButton.setOnClickListener { explainBackgroundPermission() }
        batteryButton.setOnClickListener { requestBatteryExemption() }
        findViewById<Button>(R.id.unpairButton).setOnClickListener { confirmUnpair() }
    }

    private fun confirmUnpair() {
        MaterialAlertDialogBuilder(this)
            .setTitle("Desvincular este teléfono")
            .setMessage(
                "El panel dejará de ver este teléfono y no se enviarán más avisos. " +
                    "Puedes volver a emparejarlo con un código nuevo.",
            )
            .setPositiveButton("Desvincular") { _, _ ->
                GeoService.stop(this)
                Prefs.clear(this)
                showSetup()
                Toast.makeText(this, "Teléfono desvinculado", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun neededPermissions(): Array<String> {
        val permissions = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.RECEIVE_SMS,
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        return permissions.toTypedArray()
    }

    private fun granted(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun batteryOptimizationIgnored(): Boolean {
        val manager = getSystemService(PowerManager::class.java) ?: return true
        return manager.isIgnoringBatteryOptimizations(packageName)
    }

    private fun updatePermissionUi() {
        val fine = granted(Manifest.permission.ACCESS_FINE_LOCATION)
        val background = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            granted(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        val sms = granted(Manifest.permission.RECEIVE_SMS)
        val notifications = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            granted(Manifest.permission.POST_NOTIFICATIONS)
        val battery = batteryOptimizationIgnored()

        val missing = buildList {
            if (!fine) add("ubicación")
            if (!background) add("ubicación en segundo plano")
            if (!sms) add("SMS")
            if (!notifications) add("notificaciones")
            if (!battery) add("sin ahorro de batería")
        }

        permStatus.text = if (missing.isEmpty()) {
            "Todo listo: la protección funciona en segundo plano."
        } else {
            "Pendiente: ${missing.joinToString(", ")}."
        }
        permStatus.setTextColor(
            ContextCompat.getColor(
                this,
                if (missing.isEmpty()) R.color.ok else R.color.warn,
            ),
        )
        permButton.text = if (fine && sms && notifications) "Revisar permisos" else "Conceder permisos"
        backgroundButton.isEnabled = fine
        batteryButton.isEnabled = !battery
        batteryButton.text = if (battery) {
            "Ahorro de batería desactivado ✓"
        } else {
            "Quitar ahorro de batería"
        }
    }

    private fun explainBackgroundPermission() {
        if (granted(Manifest.permission.ACCESS_BACKGROUND_LOCATION)) {
            Toast.makeText(this, "La ubicación en segundo plano ya está activa.", Toast.LENGTH_SHORT).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setTitle("Ubicación siempre activa")
            .setMessage(
                "Para proteger a tu hijo cuando la pantalla está apagada, elige " +
                    "«Permitir todo el tiempo» en Permisos → Ubicación.",
            )
            .setPositiveButton("Abrir ajustes") { _, _ ->
                val intent = Intent(
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.fromParts("package", packageName, null),
                )
                runCatching { startActivity(intent) }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun requestBatteryExemption() {
        if (batteryOptimizationIgnored()) {
            Toast.makeText(this, "El ahorro de batería ya está desactivado.", Toast.LENGTH_SHORT).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setTitle("Evitar que Android cierre la app")
            .setMessage(
                "Muchos teléfonos suspenden las apps en segundo plano. Exime a GeoSms911 " +
                    "del ahorro de batería para que siga enviando tu ubicación.",
            )
            .setPositiveButton("Permitir") { _, _ ->
                val intent = Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:$packageName"),
                )
                runCatching { startActivity(intent) }
            }
            .setNegativeButton("Ahora no", null)
            .show()
    }

    private fun pairDevice() {
        val rawServer = serverInput.text?.toString().orEmpty()
        val server = normalizeServer(rawServer)
        val code = codeInput.text?.toString().orEmpty().trim()
        val name = nameInput.text?.toString().orEmpty().trim().ifBlank {
            "${Build.MANUFACTURER} ${Build.MODEL}"
        }
        val phone = phoneInput.text?.toString().orEmpty().trim()

        if (server.isBlank()) {
            showSetupError("Escribe la dirección del servidor, por ejemplo https://mi-servidor.com")
            return
        }
        if (!code.matches(Regex("\\d{4,10}"))) {
            showSetupError("El código debe tener al menos 4 dígitos.")
            return
        }

        setupError.visibility = View.GONE
        pairButton.isEnabled = false
        pairButton.text = "Emparejando…"

        lifecycleScope.launch {
            val previousServer = Prefs.serverUrl(this@MainActivity)
            Prefs.setServerUrl(this@MainActivity, server)
            try {
                val data = withContext(Dispatchers.IO) {
                    Api(this@MainActivity).register(code, name, phone.ifBlank { null })
                }
                Prefs.savePairing(
                    this@MainActivity,
                    server,
                    data.getString("device_id"),
                    data.getString("device_token"),
                    data.optString("sms_secret"),
                    data.optString("sms_prefix", "GEOSMS911"),
                    data.optString("emergency_number", "911"),
                    name,
                )
                codeInput.setText("")
                showHome()
                updatePermissionUi()
                permissionLauncher.launch(neededPermissions())
                GeoService.start(this@MainActivity)
                Toast.makeText(
                    this@MainActivity,
                    "Teléfono emparejado. La protección está activa.",
                    Toast.LENGTH_LONG,
                ).show()
            } catch (error: Exception) {
                Prefs.setServerUrl(this@MainActivity, previousServer)
                showSetupError(error.message ?: "No se pudo emparejar. Revisa la URL y el código.")
            } finally {
                pairButton.isEnabled = true
                pairButton.text = "Emparejar"
            }
        }
    }

    private fun normalizeServer(raw: String): String {
        var value = raw.trim().trimEnd('/')
        if (value.isBlank()) return ""
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://$value"
        }
        return value
    }

    private fun showSetupError(message: String) {
        setupError.text = message
        setupError.visibility = View.VISIBLE
    }

    private fun showSetup() {
        setupCard.visibility = View.VISIBLE
        homeCard.visibility = View.GONE
        permCard.visibility = View.GONE
        chipStatus.text = "Sin emparejar"
        chipStatus.setTextColor(ContextCompat.getColor(this, R.color.muted))
        chipStatus.setBackgroundResource(R.drawable.bg_chip)
    }

    private fun showHome() {
        setupCard.visibility = View.GONE
        homeCard.visibility = View.VISIBLE
        permCard.visibility = View.VISIBLE
        chipStatus.text = "Protegido"
        chipStatus.setTextColor(ContextCompat.getColor(this, R.color.ok))
        chipStatus.setBackgroundResource(R.drawable.bg_chip_ok)
        homeTitle.text = Prefs.deviceName(this)
        refreshHome()
    }

    private fun refreshHome() {
        val syncedAt = Prefs.lastSyncAt(this)
        lastSyncText.text = if (syncedAt == 0L) {
            "Aún sin sincronizar con el servidor"
        } else {
            "Última sincronización: " + DateUtils.getRelativeTimeSpanString(
                syncedAt,
                System.currentTimeMillis(),
                DateUtils.MINUTE_IN_MILLIS,
            )
        }

        val fine = granted(Manifest.permission.ACCESS_FINE_LOCATION)
        val background = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            granted(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        homeSubtitle.text = when {
            !fine -> "Falta el permiso de ubicación"
            !background -> "Protección activa mientras la app está abierta"
            !batteryOptimizationIgnored() -> "Protección activa · revisa el ahorro de batería"
            else -> "Protección activa en segundo plano"
        }
    }

    private fun startHold() {
        if (holdJob != null) return
        if (!Prefs.isPaired(this)) {
            Toast.makeText(this, "Primero empareja el teléfono.", Toast.LENGTH_SHORT).show()
            return
        }
        sosProgress.visibility = View.VISIBLE
        sosProgress.progress = 0
        AlarmPlayer.vibrate(this, 40)

        holdJob = lifecycleScope.launch {
            for (step in 1..30) {
                delay(100)
                sosProgress.progress = step * 100 / 30
                if (step % 6 == 0) AlarmPlayer.vibrate(this@MainActivity, 30)
            }
            holdJob = null
            sosProgress.visibility = View.INVISIBLE
            triggerPanic()
        }
    }

    private fun cancelHold() {
        holdJob?.cancel()
        holdJob = null
        sosProgress.progress = 0
        sosProgress.visibility = View.INVISIBLE
    }

    private fun triggerPanic() {
        if (!Prefs.isPaired(this)) return
        sosButton.isEnabled = false
        homeSubtitle.text = "Enviando alerta…"
        AlarmPlayer.vibrate(this, 350)

        val location = bestLastKnownLocation()
        val cached = Prefs.lastFix(this)

        lifecycleScope.launch {
            val sent = withContext(Dispatchers.IO) {
                Api(this@MainActivity).sendAlert(
                    location?.latitude ?: cached?.first,
                    location?.longitude ?: cached?.second,
                    location?.accuracy?.toDouble(),
                    batteryLevel(),
                    "Botón de pánico del teléfono",
                )
            }
            sosButton.isEnabled = true
            if (sent) {
                homeSubtitle.text = "Alerta enviada. Tu tutor fue notificado."
                Toast.makeText(
                    this@MainActivity,
                    "Alerta enviada a tu tutor.",
                    Toast.LENGTH_LONG,
                ).show()
            } else {
                homeSubtitle.text = "No se pudo enviar la alerta. Revisa la conexión."
                Toast.makeText(
                    this@MainActivity,
                    "Sin conexión con el servidor. Intenta de nuevo.",
                    Toast.LENGTH_LONG,
                ).show()
            }
            GeoService.sendNow(this@MainActivity)
        }
    }

    private fun bestLastKnownLocation(): Location? {
        if (!granted(Manifest.permission.ACCESS_FINE_LOCATION) &&
            !granted(Manifest.permission.ACCESS_COARSE_LOCATION)
        ) {
            return null
        }
        val manager = getSystemService(LocationManager::class.java) ?: return null
        return manager.getProviders(true)
            .mapNotNull { provider ->
                runCatching { manager.getLastKnownLocation(provider) }.getOrNull()
            }
            .maxByOrNull { it.time }
    }

    private fun batteryLevel(): Int {
        val manager = getSystemService(android.os.BatteryManager::class.java) ?: return 0
        return manager.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)
            .coerceIn(0, 100)
    }

    private fun openMap() {
        val fix = Prefs.lastFix(this)
        val uri = if (fix != null) {
            Uri.parse("geo:${fix.first},${fix.second}?q=${fix.first},${fix.second}(Mi%20ubicaci%C3%B3n)")
        } else {
            Uri.parse("geo:0,0?q=mi%20ubicacion")
        }
        runCatching { startActivity(Intent(Intent.ACTION_VIEW, uri)) }
    }

    private fun handleDeepLink(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme == "geosms911" && Prefs.isPaired(this)) {
            GeoService.sendNow(this)
        }
    }
}
