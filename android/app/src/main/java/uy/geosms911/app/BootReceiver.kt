package uy.geosms911.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Reinicia la protección después de apagar o actualizar el teléfono. */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (!Prefs.isPaired(context)) return
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_LOCKED_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            -> {
                Notifications.ensureChannels(context)
                GeoService.start(context)
            }
        }
    }
}
