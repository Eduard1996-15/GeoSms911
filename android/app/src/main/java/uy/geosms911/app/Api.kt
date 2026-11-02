package uy.geosms911.app

import android.content.Context
import android.os.Build
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiException(message: String) : IOException(message)

/** Cliente HTTP minimo contra el backend de GeoSms911. */
class Api(context: Context) {

    private val appContext = context.applicationContext

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .build()

    private val jsonType = "application/json; charset=utf-8".toMediaType()

    private fun base(): String {
        val server = Prefs.serverUrl(appContext).trim().trimEnd('/')
        if (server.isBlank()) throw ApiException("El servidor no está configurado")
        return server
    }

    private fun authorized(path: String): Request.Builder {
        val builder = Request.Builder().url(base() + path)
        if (Prefs.isPaired(appContext)) {
            builder.header("X-Device-Id", Prefs.deviceId(appContext))
            builder.header("X-Device-Token", Prefs.deviceToken(appContext))
        }
        return builder
    }

    private fun execute(request: Request): JSONObject {
        client.newCall(request).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrDefault("")
                throw ApiException(detail.ifBlank { "Error ${response.code}" })
            }
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        }
    }

    private fun postJson(path: String, payload: JSONObject, authenticated: Boolean = true): JSONObject {
        val builder = if (authenticated) authorized(path) else Request.Builder().url(base() + path)
        return execute(builder.post(payload.toString().toRequestBody(jsonType)).build())
    }

    fun register(code: String, name: String, phone: String?): JSONObject {
        val payload = JSONObject()
            .put("code", code)
            .put("name", name)
            .put("platform", "android")
            .put("model_name", "${Build.MANUFACTURER} ${Build.MODEL}")
            .put("app_version", BuildConfig.VERSION_NAME)
        if (!phone.isNullOrBlank()) payload.put("phone", phone)
        return postJson("/api/devices/register", payload, authenticated = false)
    }

    fun me(): JSONObject = execute(authorized("/api/ingest/me").get().build())

    fun heartbeat(battery: Int, sharing: Boolean): Boolean = runCatching {
        val payload = JSONObject()
            .put("battery", battery)
            .put("location_sharing", sharing)
            .put("app_version", BuildConfig.VERSION_NAME)
        postJson("/api/ingest/heartbeat", payload)
        true
    }.getOrDefault(false)

    fun sendLocation(
        lat: Double,
        lng: Double,
        accuracy: Double?,
        battery: Int?,
        source: String = "app",
    ): Boolean = runCatching {
        val payload = JSONObject()
            .put("lat", lat)
            .put("lng", lng)
            .put("source", source)
        if (accuracy != null) payload.put("accuracy", accuracy)
        if (battery != null) payload.put("battery", battery)
        postJson("/api/ingest/location", payload)
        Prefs.saveFix(appContext, lat, lng)
        Prefs.markSynced(appContext)
        true
    }.getOrDefault(false)

    fun sendAlert(
        lat: Double?,
        lng: Double?,
        accuracy: Double?,
        battery: Int?,
        message: String?,
    ): Boolean = runCatching {
        val payload = JSONObject().put("kind", "panic")
        if (lat != null && lng != null) {
            payload.put("lat", lat).put("lng", lng)
        }
        if (accuracy != null) payload.put("accuracy", accuracy)
        if (battery != null) payload.put("battery", battery)
        if (!message.isNullOrBlank()) payload.put("message", message)
        postJson("/api/ingest/alert", payload)
        true
    }.getOrDefault(false)

    fun commands(waitSeconds: Int): JSONArray {
        val data = execute(
            authorized("/api/ingest/commands?wait=$waitSeconds").get().build(),
        )
        return data.optJSONArray("commands") ?: JSONArray()
    }

    fun ack(commandId: String, status: String, result: JSONObject?, error: String? = null): Boolean =
        runCatching {
            val payload = JSONObject().put("status", status)
            if (result != null) payload.put("result", result)
            if (!error.isNullOrBlank()) payload.put("error", error.take(400))
            postJson("/api/ingest/commands/$commandId/ack", payload)
            true
        }.getOrDefault(false)

    fun isRevokedError(error: Throwable): Boolean {
        val text = error.message.orEmpty()
        return text.contains("autorizado", ignoreCase = true) ||
            text.contains("revocado", ignoreCase = true)
    }
}
