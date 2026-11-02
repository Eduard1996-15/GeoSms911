package uy.geosms911.app

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.text.DateFormat
import java.util.Date

/** Pantalla de emergencia que se abre cuando el tutor envía un aviso. */
class AlertActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_TITLE = "title"
        const val EXTRA_MESSAGE = "message"
        const val EXTRA_NUMBER = "number"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        }
        @Suppress("DEPRECATION")
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD or
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED,
        )

        setContentView(R.layout.activity_alert)

        val emergency = Prefs.emergencyNumber(this)
        val title = intent.getStringExtra(EXTRA_TITLE)
            ?: "Tu familia te está buscando"
        val message = intent.getStringExtra(EXTRA_MESSAGE)
            ?: "Se activó un aviso desde el panel familiar."

        findViewById<TextView>(R.id.alertTitle).text = title
        findViewById<TextView>(R.id.alertMessage).text = message
        findViewById<TextView>(R.id.alertTime).text =
            DateFormat.getTimeInstance(DateFormat.SHORT).format(Date())

        findViewById<Button>(R.id.call911Button).apply {
            text = "Llamar al $emergency"
            setOnClickListener { dial(emergency) }
        }

        val familyNumber = intent.getStringExtra(EXTRA_NUMBER)
        findViewById<Button>(R.id.callFamilyButton).apply {
            if (familyNumber.isNullOrBlank()) {
                visibility = Button.GONE
            } else {
                visibility = Button.VISIBLE
                setOnClickListener { dial(familyNumber) }
            }
        }

        findViewById<Button>(R.id.shareLocationButton).setOnClickListener {
            GeoService.sendNow(this)
            Toast.makeText(this, "Compartiendo tu ubicación…", Toast.LENGTH_SHORT).show()
        }

        findViewById<Button>(R.id.safeButton).setOnClickListener {
            AlarmPlayer.stop()
            AlarmPlayer.cancelVibration(this)
            Notifications.cancelAlert(this)
            finish()
        }

        AlarmPlayer.vibratePattern(this)
    }

    override fun onDestroy() {
        AlarmPlayer.cancelVibration(this)
        super.onDestroy()
    }

    /** Solo abre el marcador: nunca llama por su cuenta. */
    private fun dial(number: String) {
        val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number"))
        runCatching { startActivity(intent) }
            .onFailure {
                Toast.makeText(this, "No se pudo abrir el marcador", Toast.LENGTH_SHORT).show()
            }
    }
}
