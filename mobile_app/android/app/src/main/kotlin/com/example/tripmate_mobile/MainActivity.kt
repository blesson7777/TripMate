package com.example.tripmate_mobile

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Environment
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            UPDATE_CHANNEL,
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "enqueueApkDownload" -> {
                    val url = call.argument<String>("url")?.trim().orEmpty()
                    if (url.isEmpty()) {
                        result.error("missing_url", "Download URL is required.", null)
                        return@setMethodCallHandler
                    }

                    val fileName = call.argument<String>("fileName")?.trim()
                        ?.takeIf { it.isNotEmpty() }
                        ?: "tripmate_update.apk"
                    val title = call.argument<String>("title")?.trim()
                        ?.takeIf { it.isNotEmpty() }
                        ?: "TripMate update"
                    val description = call.argument<String>("description")?.trim()
                        ?.takeIf { it.isNotEmpty() }
                        ?: "Downloading update in background."

                    try {
                        val request = DownloadManager.Request(Uri.parse(url))
                            .setTitle(title)
                            .setDescription(description)
                            .setNotificationVisibility(
                                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED,
                            )
                            .setMimeType(APK_MIME_TYPE)
                            .setAllowedOverMetered(true)
                            .setAllowedOverRoaming(true)
                            .setVisibleInDownloadsUi(true)
                            .setDestinationInExternalPublicDir(
                                Environment.DIRECTORY_DOWNLOADS,
                                fileName,
                            )

                        val manager = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
                        val downloadId = manager.enqueue(request)
                        UpdateDownloadStore.trackDownload(applicationContext, downloadId)
                        result.success(downloadId.toString())
                    } catch (error: Exception) {
                        result.error(
                            "enqueue_failed",
                            error.message ?: "Unable to start background download.",
                            null,
                        )
                    }
                }

                else -> result.notImplemented()
            }
        }
    }

    companion object {
        private const val UPDATE_CHANNEL = "tripmate/update_manager"
        private const val APK_MIME_TYPE = "application/vnd.android.package-archive"
    }
}

internal object UpdateDownloadStore {
    private const val PREFS_NAME = "tripmate_update_downloads"
    private const val KEY_IDS = "download_ids"

    fun trackDownload(context: Context, downloadId: Long) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val ids = prefs.getStringSet(KEY_IDS, emptySet())?.toMutableSet() ?: mutableSetOf()
        ids.add(downloadId.toString())
        prefs.edit().putStringSet(KEY_IDS, ids).apply()
    }

    fun isTracked(context: Context, downloadId: Long): Boolean {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val ids = prefs.getStringSet(KEY_IDS, emptySet()) ?: emptySet()
        return ids.contains(downloadId.toString())
    }

    fun remove(context: Context, downloadId: Long) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val ids = prefs.getStringSet(KEY_IDS, emptySet())?.toMutableSet() ?: mutableSetOf()
        ids.remove(downloadId.toString())
        prefs.edit().putStringSet(KEY_IDS, ids).apply()
    }
}
