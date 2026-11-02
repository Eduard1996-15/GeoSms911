package uy.geosms911.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import org.json.JSONObject

/**
 * Respaldo por SMS: si el teléfono no tiene datos, el tutor puede enviar
 * "GEOSMS911 <clave> CMD <id> <orden>" y el teléfono actúa igual.
 */
class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        if (!Prefs.isPaired(context)) return

        val secret = Prefs.smsSecret(context)
        if (secret.isBlank()) return

        val body = runCatching {
            Telephony.Sms.Intents.getMessagesFromIntent(intent)
                ?.joinToString("") { it.messageBody ?: "" }
        }.getOrNull().orEmpty()
        if (body.isBlank()) return

        val prefix = Prefs.smsPrefix(context).ifBlank { "GEOSMS911" }
        val pattern = Regex(
            "(?i)\\b${Regex.escape(prefix)}\\s+${Regex.escape(secret)}\\s+CMD\\s+([A-Za-z0-9]+)\\s+([A-Za-z_]+)",
        )
        val match = pattern.find(body) ?: return
        val commandId = match.groupValues[1]
        val kind = match.groupValues[2].lowercase()

        val pending = goAsync()
        Thread {
            try {
                handle(context, commandId, kind)
            } catch (_: Exception) {
                // El servicio reintentará cuando haya conexión.
            } finally {
                pending.finish()
            }
        }.start()

        // Asegura que el servicio vuelva a estar activo tras el SMS.
        GeoService.start(context)
    }

    private fun handle(context: Context, commandId: String, kind: String) {
        val api = Api(context)
        var result: JSONObject? = null
        var failure: String? = null

        when (kind) {
            "ring" -> {
                AlarmPlayer.start(context)
                Notifications.postAlert(
                    context,
                    "Alarma activada",
                    "Tu tutor activó la alarma de este teléfono.",
                    false,
                )
            }
            "stop_ring" -> {
                AlarmPlayer.stop()
                AlarmPlayer.cancelVibration(context)
                Notifications.cancelAlert(context)
            }
            "alert_screen" -> Notifications.postAlert(
                context,
                "Tu familia te está buscando",
                "Tu tutor envió un aviso. Abre GeoSms911 si necesitas ayuda.",
                true,
            )
            "locate" -> {
                val fix = Prefs.lastFix(context)
                if (fix != null) {
                    api.sendLocation(fix.first, fix.second, null, null, "sms")
                    result = JSONObject().put("lat", fix.first).put("lng", fix.second)
                } else {
                    failure = "Sin ubicación en caché"
                }
            }
            "sync" -> {
                val fix = Prefs.lastFix(context)
                if (fix != null) {
                    api.sendLocation(fix.first, fix.second, null, null, "sms")
                    result = JSONObject().put("lat", fix.first).put("lng", fix.second)
                }
            }
            else -> Unit
        }

        api.ack(commandId, if (failure == null) "acked" else "failed", result, failure)
    }
}
