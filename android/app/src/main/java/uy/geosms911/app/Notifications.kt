package uy.geosms911.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

/** Canales y notificaciones de la app. */
object Notifications {

    const val CHANNEL_SERVICE = "geosms_service"
    const val CHANNEL_ALERTS = "geosms_alerts"
    const val CHANNEL_STATUS = "geosms_status"

    const val SERVICE_ID = 1001
    const val ALERT_ID = 2001

    fun ensureChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java) ?: return

        val service = NotificationChannel(
            CHANNEL_SERVICE,
            "Protección activa",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Mantiene la ubicación y las órdenes activas."
            setShowBadge(false)
        }

        val alerts = NotificationChannel(
            CHANNEL_ALERTS,
            "Alertas de emergencia",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Avisos de tu tutor y alarmas del teléfono."
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 500, 250, 500)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }

        val status = NotificationChannel(
            CHANNEL_STATUS,
            "Estado del servicio",
            NotificationManager.IMPORTANCE_DEFAULT,
        )

        manager.createNotificationChannels(listOf(service, alerts, status))
    }

    private fun openAppIntent(context: Context): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        return PendingIntent.getActivity(
            context,
            10,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    fun serviceNotification(context: Context, text: String): Notification =
        NotificationCompat.Builder(context, CHANNEL_SERVICE)
            .setSmallIcon(R.drawable.ic_stat_shield)
            .setContentTitle("GeoSms911")
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setContentIntent(openAppIntent(context))
            .build()

    fun updateServiceNotification(context: Context, text: String) {
        runCatching {
            NotificationManagerCompat.from(context)
                .notify(SERVICE_ID, serviceNotification(context, text))
        }
    }

    fun alertNotification(
        context: Context,
        title: String,
        message: String,
        fullScreen: Boolean,
        number: String? = null,
    ): Notification {
        val intent = Intent(context, AlertActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(AlertActivity.EXTRA_TITLE, title)
            putExtra(AlertActivity.EXTRA_MESSAGE, message)
            if (number != null) putExtra(AlertActivity.EXTRA_NUMBER, number)
        }
        val pending = PendingIntent.getActivity(
            context,
            20,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_shield)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .setDefaults(NotificationCompat.DEFAULT_ALL)

        if (fullScreen) {
            builder.setFullScreenIntent(pending, true)
        }
        return builder.build()
    }

    fun postAlert(
        context: Context,
        title: String,
        message: String,
        fullScreen: Boolean,
        number: String? = null,
    ) {
        runCatching {
            NotificationManagerCompat.from(context)
                .notify(ALERT_ID, alertNotification(context, title, message, fullScreen, number))
        }
    }

    fun postStatus(context: Context, title: String, message: String) {
        val builder = NotificationCompat.Builder(context, CHANNEL_STATUS)
            .setSmallIcon(R.drawable.ic_stat_shield)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setAutoCancel(true)
            .setContentIntent(openAppIntent(context))
        runCatching {
            NotificationManagerCompat.from(context).notify(3001, builder.build())
        }
    }

    fun cancelAlert(context: Context) {
        runCatching { NotificationManagerCompat.from(context).cancel(ALERT_ID) }
    }

    @Suppress("unused")
    private fun audioAttributes(): AudioAttributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ALARM)
        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
        .build()
}
