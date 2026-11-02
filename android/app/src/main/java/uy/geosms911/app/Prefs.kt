package uy.geosms911.app

import android.content.Context

/** Almacenamiento local de la configuracion del dispositivo. */
object Prefs {

    private const val FILE = "geosms911"
    private const val KEY_SERVER = "server_url"
    private const val KEY_DEVICE_ID = "device_id"
    private const val KEY_TOKEN = "device_token"
    private const val KEY_SMS_SECRET = "sms_secret"
    private const val KEY_SMS_PREFIX = "sms_prefix"
    private const val KEY_EMERGENCY = "emergency_number"
    private const val KEY_NAME = "device_name"
    private const val KEY_SHARING = "sharing"
    private const val KEY_LAST_SYNC = "last_sync"
    private const val KEY_LAST_LAT = "last_lat"
    private const val KEY_LAST_LNG = "last_lng"
    private const val KEY_LAST_FIX = "last_fix_at"
    private const val KEY_HAS_FIX = "has_fix"

    private fun sp(context: Context) =
        context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun serverUrl(context: Context): String = sp(context).getString(KEY_SERVER, "") ?: ""

    fun setServerUrl(context: Context, value: String) {
        sp(context).edit().putString(KEY_SERVER, value).apply()
    }

    fun deviceId(context: Context): String = sp(context).getString(KEY_DEVICE_ID, "") ?: ""

    fun deviceToken(context: Context): String = sp(context).getString(KEY_TOKEN, "") ?: ""

    fun smsSecret(context: Context): String = sp(context).getString(KEY_SMS_SECRET, "") ?: ""

    fun smsPrefix(context: Context): String =
        sp(context).getString(KEY_SMS_PREFIX, "GEOSMS911") ?: "GEOSMS911"

    fun emergencyNumber(context: Context): String =
        sp(context).getString(KEY_EMERGENCY, "911") ?: "911"

    fun deviceName(context: Context): String =
        sp(context).getString(KEY_NAME, "Mi teléfono") ?: "Mi teléfono"

    fun sharing(context: Context): Boolean = sp(context).getBoolean(KEY_SHARING, true)

    fun setSharing(context: Context, value: Boolean) {
        sp(context).edit().putBoolean(KEY_SHARING, value).apply()
    }

    fun lastSyncAt(context: Context): Long = sp(context).getLong(KEY_LAST_SYNC, 0L)

    fun markSynced(context: Context) {
        sp(context).edit().putLong(KEY_LAST_SYNC, System.currentTimeMillis()).apply()
    }

    fun hasFix(context: Context): Boolean = sp(context).getBoolean(KEY_HAS_FIX, false)

    fun lastFix(context: Context): Triple<Double, Double, Long>? {
        if (!hasFix(context)) return null
        val prefs = sp(context)
        return Triple(
            prefs.getFloat(KEY_LAST_LAT, 0f).toDouble(),
            prefs.getFloat(KEY_LAST_LNG, 0f).toDouble(),
            prefs.getLong(KEY_LAST_FIX, 0L),
        )
    }

    fun saveFix(context: Context, lat: Double, lng: Double) {
        sp(context).edit()
            .putBoolean(KEY_HAS_FIX, true)
            .putFloat(KEY_LAST_LAT, lat.toFloat())
            .putFloat(KEY_LAST_LNG, lng.toFloat())
            .putLong(KEY_LAST_FIX, System.currentTimeMillis())
            .apply()
    }

    fun isPaired(context: Context): Boolean =
        deviceId(context).isNotBlank() && deviceToken(context).isNotBlank()

    fun savePairing(
        context: Context,
        serverUrl: String,
        deviceId: String,
        token: String,
        smsSecret: String,
        smsPrefix: String,
        emergencyNumber: String,
        deviceName: String,
    ) {
        sp(context).edit()
            .putString(KEY_SERVER, serverUrl)
            .putString(KEY_DEVICE_ID, deviceId)
            .putString(KEY_TOKEN, token)
            .putString(KEY_SMS_SECRET, smsSecret)
            .putString(KEY_SMS_PREFIX, smsPrefix)
            .putString(KEY_EMERGENCY, emergencyNumber)
            .putString(KEY_NAME, deviceName)
            .putBoolean(KEY_SHARING, true)
            .apply()
    }

    fun clear(context: Context) {
        val server = serverUrl(context)
        sp(context).edit().clear().apply()
        setServerUrl(context, server)
    }
}
