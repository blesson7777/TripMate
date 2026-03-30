package com.example.tripmate_mobile

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.os.Build
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.max

class TripTrackingForegroundService : Service() {
    private val ioExecutor = Executors.newSingleThreadExecutor()
    private val trackingPrefs by lazy {
        getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }
    private val flutterPrefs by lazy {
        getSharedPreferences(FLUTTER_PREFS_NAME, Context.MODE_PRIVATE)
    }

    private val fusedClient by lazy {
        LocationServices.getFusedLocationProviderClient(this)
    }

    private var callback: LocationCallback? = null
    private var started = false

    @Volatile
    private var uploadInFlight = false

    private var lastSentAtElapsedMs: Long? = null
    private var lastSentLocation: Location? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START
        when (action) {
            ACTION_STOP -> {
                stopTracking()
                stopForegroundCompat()
                stopSelf()
                return START_NOT_STICKY
            }

            ACTION_START -> {
                val baseUrlExtra = intent?.getStringExtra(EXTRA_BASE_URL)
                if (!baseUrlExtra.isNullOrBlank()) {
                    trackingPrefs.edit().putString(KEY_BASE_URL, baseUrlExtra.trim()).apply()
                }

                val baseUrl = trackingPrefs.getString(KEY_BASE_URL, "")?.trim().orEmpty()
                if (baseUrl.isEmpty()) {
                    stopSelf()
                    return START_NOT_STICKY
                }

                startAsForeground()
                startTracking()
                return START_STICKY
            }

            else -> return START_STICKY
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Keep tracking alive even when the app is swiped away from Recents.
        // This schedules a gentle restart; if the service is still running,
        // the START handler is idempotent and will not duplicate location callbacks.
        scheduleRestart()
        super.onTaskRemoved(rootIntent)
    }

    private fun scheduleRestart() {
        val restartIntent = Intent(applicationContext, TripTrackingForegroundService::class.java).apply {
            action = ACTION_START
        }
        val pending = PendingIntent.getService(
            applicationContext,
            RESTART_REQUEST_CODE,
            restartIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val alarm = getSystemService(Context.ALARM_SERVICE) as AlarmManager
        alarm.set(
            AlarmManager.ELAPSED_REALTIME,
            SystemClock.elapsedRealtime() + 1500,
            pending,
        )
    }

    private fun startAsForeground() {
        ensureNotificationChannel()
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("TripMate trip tracking is active")
            .setContentText("Location monitoring stays active while your trip is open.")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        startForeground(NOTIFICATION_ID, notification)
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val existing = manager.getNotificationChannel(CHANNEL_ID)
        if (existing != null) {
            return
        }
        val channel = NotificationChannel(
            CHANNEL_ID,
            "TripMate Tracking",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Foreground tracking while trips are open"
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun startTracking() {
        if (started) {
            return
        }
        if (!hasLocationPermission()) {
            return
        }

        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 60_000L)
            .setMinUpdateIntervalMillis(30_000L)
            .setMinUpdateDistanceMeters(75f)
            .build()

        callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val location = result.lastLocation ?: return
                handleLocation(location)
            }
        }

        fusedClient.requestLocationUpdates(
            request,
            callback!!,
            Looper.getMainLooper(),
        )
        started = true
    }

    private fun stopTracking() {
        callback?.let {
            fusedClient.removeLocationUpdates(it)
        }
        callback = null
        started = false
        uploadInFlight = false
        lastSentAtElapsedMs = null
        lastSentLocation = null
    }

    private fun handleLocation(location: Location) {
        if (uploadInFlight) {
            return
        }

        val shouldUpload = shouldUpload(location)
        if (!shouldUpload) {
            return
        }

        uploadInFlight = true
        ioExecutor.execute {
            try {
                val ok = postLocationToBackend(location)
                if (ok) {
                    lastSentAtElapsedMs = SystemClock.elapsedRealtime()
                    lastSentLocation = location
                }
            } finally {
                uploadInFlight = false
            }
        }
    }

    private fun shouldUpload(location: Location): Boolean {
        val lastAt = lastSentAtElapsedMs
        val lastLoc = lastSentLocation
        if (lastAt == null || lastLoc == null) {
            return true
        }

        val elapsedMs = SystemClock.elapsedRealtime() - lastAt
        val distance = lastLoc.distanceTo(location).toDouble()

        val currentAcc = if (location.hasAccuracy()) location.accuracy.toDouble() else 0.0
        val lastAcc = if (lastLoc.hasAccuracy()) lastLoc.accuracy.toDouble() else 0.0
        val effectiveMinDistance = max(75.0, currentAcc + lastAcc)

        val speedMps = if (location.hasSpeed() && location.speed >= 0) location.speed.toDouble() else null
        val isMoving = (speedMps != null && speedMps >= 1.0) ||
            distance >= max(effectiveMinDistance, 200.0)

        val minIntervalMs = if (isMoving) 60_000L else 300_000L

        return if (isMoving) {
            distance >= effectiveMinDistance || elapsedMs >= minIntervalMs
        } else {
            elapsedMs >= minIntervalMs
        }
    }

    private fun postLocationToBackend(location: Location): Boolean {
        val baseUrl = trackingPrefs.getString(KEY_BASE_URL, "")?.trim().orEmpty()
        if (baseUrl.isEmpty()) {
            return false
        }

        val accessToken = readAccessToken()
        if (accessToken.isNullOrBlank()) {
            return false
        }

        val endpoint = baseUrl.trimEnd('/') + "/attendance/track-location"
        val body = JSONObject().apply {
            put("latitude", formatCoord(location.latitude))
            put("longitude", formatCoord(location.longitude))
            if (location.hasAccuracy()) {
                put("accuracy_m", String.format(Locale.US, "%.2f", location.accuracy.toDouble()))
            }
            if (location.hasSpeed() && location.speed >= 0) {
                put("speed_kph", String.format(Locale.US, "%.2f", location.speed.toDouble() * 3.6))
            }
            put("recorded_at", Instant.ofEpochMilli(location.time).toString())
        }

        val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 15_000
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Authorization", "Bearer $accessToken")
        }

        return try {
            connection.outputStream.use { output ->
                output.write(body.toString().toByteArray(Charsets.UTF_8))
            }
            val code = connection.responseCode
            if (code in 200..299) {
                return true
            }

            val errorBody = try {
                connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
            } catch (_: Exception) {
                ""
            }.lowercase()

            if (code == 401 || code == 403) {
                stopAndTerminate()
            } else if (code == 400) {
                if (errorBody.contains("no active run") ||
                    errorBody.contains("no active") ||
                    errorBody.contains("disabled")
                ) {
                    stopAndTerminate()
                }
            }

            false
        } catch (_: Exception) {
            false
        } finally {
            connection.disconnect()
        }
    }

    private fun stopAndTerminate() {
        stopTracking()
        stopForegroundCompat()
        stopSelf()
    }

    @Suppress("DEPRECATION")
    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            stopForeground(true)
        }
    }

    private fun readAccessToken(): String? {
        val raw = flutterPrefs.getString(FLUTTER_KEY_SESSION, null) ?: return null
        return try {
            val json = JSONObject(raw)
            json.optString("access", "").trim().takeIf { it.isNotEmpty() }
        } catch (_: Exception) {
            null
        }
    }

    private fun hasLocationPermission(): Boolean {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
        val coarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION)
        return fine == PackageManager.PERMISSION_GRANTED || coarse == PackageManager.PERMISSION_GRANTED
    }

    private fun formatCoord(value: Double): String {
        return String.format(Locale.US, "%.6f", value)
    }

    companion object {
        const val ACTION_START = "tripmate.TRACKING_START"
        const val ACTION_STOP = "tripmate.TRACKING_STOP"
        const val EXTRA_BASE_URL = "base_url"

        private const val CHANNEL_ID = "tripmate_tracking"
        private const val NOTIFICATION_ID = 9201
        private const val RESTART_REQUEST_CODE = 9202

        private const val PREFS_NAME = "tripmate_tracking_prefs"
        private const val KEY_BASE_URL = "api_base_url"

        private const val FLUTTER_PREFS_NAME = "FlutterSharedPreferences"
        private const val FLUTTER_KEY_SESSION = "flutter.tripmate_auth_session"
    }
}
