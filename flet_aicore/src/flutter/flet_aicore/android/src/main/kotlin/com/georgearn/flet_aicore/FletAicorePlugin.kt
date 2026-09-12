package com.georgearn.flet_aicore

import androidx.annotation.NonNull
import com.google.mlkit.genai.common.DownloadStatus
import com.google.mlkit.genai.common.FeatureStatus
import com.google.mlkit.genai.prompt.Generation
import com.google.mlkit.genai.prompt.TextPart
import com.google.mlkit.genai.prompt.generateContentRequest
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.MethodChannel.MethodCallHandler
import io.flutter.plugin.common.MethodChannel.Result
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Bridges Python (via flet_aicore's Dart FletService) to ML Kit's on-device
 * GenAI Prompt API (Gemini Nano / AICore). Pixel-only; requires Android 14+
 * devices where AICore is present, plus the Gemini Nano feature downloaded.
 *
 * Registered automatically by Flutter's plugin system (see pubspec.yaml's
 * `flutter.plugin.platforms.android.pluginClass`) — no manual wiring needed
 * in the host app's MainActivity/AndroidManifest.
 */
class FletAicorePlugin : FlutterPlugin, MethodCallHandler {
    private lateinit var channel: MethodChannel
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val model by lazy { Generation.getClient() }

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel = MethodChannel(binding.binaryMessenger, "com.georgearn.flet_aicore/aicore")
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onMethodCall(call: MethodCall, result: Result) {
        when (call.method) {
            "checkStatus" -> scope.launch {
                try {
                    val status = when (model.checkStatus()) {
                        FeatureStatus.UNAVAILABLE -> "unavailable"
                        FeatureStatus.DOWNLOADABLE -> "downloadable"
                        FeatureStatus.DOWNLOADING -> "downloading"
                        FeatureStatus.AVAILABLE -> "available"
                        else -> "unavailable"
                    }
                    result.success(status)
                } catch (e: Exception) {
                    result.error("CHECK_STATUS_FAILED", e.message, null)
                }
            }

            "download" -> {
                // Ack immediately — the model is ~1.5-2GB and can take minutes
                // to fetch, far longer than the invoke_method call this reply
                // unblocks on the Dart/Python side is meant to sit and wait
                // for. Progress/completion/failure are reported afterwards as
                // separate one-way channel.invokeMethod calls instead, which
                // the Dart side turns into control events.
                result.success(null)
                scope.launch {
                    try {
                        model.download().collect { status ->
                            when (status) {
                                is DownloadStatus.DownloadProgress ->
                                    channel.invokeMethod(
                                        "downloadProgress",
                                        mapOf("bytes" to status.totalBytesDownloaded)
                                    )
                                is DownloadStatus.DownloadFailed ->
                                    channel.invokeMethod(
                                        "downloadFailed",
                                        mapOf("message" to (status.e.message ?: "Download failed"))
                                    )
                                DownloadStatus.DownloadCompleted ->
                                    channel.invokeMethod("downloadComplete", null)
                                else -> { /* DownloadStarted — no-op */ }
                            }
                        }
                    } catch (e: Exception) {
                        channel.invokeMethod(
                            "downloadFailed",
                            mapOf("message" to (e.message ?: "Download failed"))
                        )
                    }
                }
            }

            "generate" -> scope.launch {
                try {
                    val prompt = call.argument<String>("prompt") ?: ""
                    val temperature = (call.argument<Double>("temperature") ?: 0.3).toFloat()
                    val topK = call.argument<Int>("top_k") ?: 16
                    val maxTokens = call.argument<Int>("max_output_tokens") ?: 1024

                    val status = model.checkStatus()
                    if (status != FeatureStatus.AVAILABLE) {
                        result.error(
                            "UNAVAILABLE",
                            "Gemini Nano status is $status, not AVAILABLE. " +
                                "Call check_status()/download() first.",
                            null
                        )
                        return@launch
                    }

                    val response = model.generateContent(
                        generateContentRequest(TextPart(prompt)) {
                            this.temperature = temperature
                            this.topK = topK
                            this.maxOutputTokens = maxTokens
                        }
                    )
                    val text = response.candidates.firstOrNull()?.text ?: ""
                    result.success(mapOf("text" to text))
                } catch (e: Exception) {
                    result.error("GENERATE_FAILED", e.message, null)
                }
            }

            else -> result.notImplemented()
        }
    }
}
