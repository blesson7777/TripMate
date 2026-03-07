package com.example.tripmate_mobile

import android.app.DownloadManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

class UpdateDownloadReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != DownloadManager.ACTION_DOWNLOAD_COMPLETE) {
            return
        }

        val downloadId = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L)
        if (downloadId <= 0L || !UpdateDownloadStore.isTracked(context, downloadId)) {
            return
        }

        val manager = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val query = DownloadManager.Query().setFilterById(downloadId)
        manager.query(query)?.use { cursor ->
            if (!cursor.moveToFirst()) {
                UpdateDownloadStore.remove(context, downloadId)
                return
            }

            val statusIndex = cursor.getColumnIndex(DownloadManager.COLUMN_STATUS)
            if (statusIndex < 0) {
                UpdateDownloadStore.remove(context, downloadId)
                return
            }

            val status = cursor.getInt(statusIndex)
            if (status == DownloadManager.STATUS_FAILED) {
                UpdateDownloadStore.remove(context, downloadId)
                return
            }
            if (status != DownloadManager.STATUS_SUCCESSFUL) {
                return
            }
        }

        val apkUri = manager.getUriForDownloadedFile(downloadId)
        UpdateDownloadStore.remove(context, downloadId)
        if (apkUri == null) {
            return
        }

        if (!launchInstaller(context, apkUri)) {
            showInstallReadyNotification(context, apkUri)
        }
    }

    private fun launchInstaller(context: Context, apkUri: Uri): Boolean {
        val launchIntent = installerIntent(context, apkUri) ?: return false
        return try {
            context.startActivity(launchIntent)
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun installerIntent(context: Context, apkUri: Uri): Intent? {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !context.packageManager.canRequestPackageInstalls()
        ) {
            return Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${context.packageName}"),
            ).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
        }

        return Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(apkUri, APK_MIME_TYPE)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }

    private fun showInstallReadyNotification(context: Context, apkUri: Uri) {
        val installIntent = installerIntent(context, apkUri) ?: return
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or
            (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                PendingIntent.FLAG_IMMUTABLE
            } else {
                0
            })
        val pendingIntent = PendingIntent.getActivity(
            context,
            10021,
            installIntent,
            flags,
        )

        ensureChannel(context)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(context.applicationInfo.icon)
            .setContentTitle("TripMate update ready")
            .setContentText("Tap to install the downloaded update.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        NotificationManagerCompat.from(context).notify(10021, notification)
    }

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            "TripMate Updates",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Installer-ready notifications for TripMate app updates"
        }
        manager.createNotificationChannel(channel)
    }

    companion object {
        private const val CHANNEL_ID = "tripmate_updates"
        private const val APK_MIME_TYPE = "application/vnd.android.package-archive"
    }
}
