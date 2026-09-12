import 'package:flet/flet.dart';
import 'package:flutter/services.dart';

/// Dart-side counterpart of Python's `AiCore` Service control.
/// Forwards Python `_invoke_method()` calls to the native Android plugin
/// (`FletAicorePlugin.kt`) over a MethodChannel, which drives
/// `com.google.mlkit:genai-prompt` (Gemini Nano / AICore).
///
/// `FletService` itself has no method-dispatch hook — incoming Python
/// `_invoke_method()` calls are delivered via `Control.addInvokeMethodListener`
/// (see `control.dart`'s `InvokeControlMethodCallback` typedef), the same
/// mechanism every widget-based control uses in its `initState`.
class AiCoreService extends FletService {
  static const _channel = MethodChannel("com.georgearn.flet_aicore/aicore");

  AiCoreService({required super.control});

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "check_status":
        return await _channel.invokeMethod<String>("checkStatus");

      case "download":
        // The native side acks this call as soon as the download *starts*
        // (a multi-hundred-MB fetch takes minutes — far longer than Flet's
        // own invoke_method dispatch is designed to block for). Progress /
        // completion / failure arrive afterwards as separate one-way calls
        // on this same channel, relayed here as control events; Python's
        // AiCore.download() awaits those events itself.
        _channel.setMethodCallHandler((call) async {
          switch (call.method) {
            case "downloadProgress":
              control.triggerEvent(
                  "download_progress", {"bytes": call.arguments["bytes"]});
              break;
            case "downloadComplete":
              control.triggerEvent("download_complete", {});
              break;
            case "downloadFailed":
              control.triggerEvent(
                  "download_failed", {"message": call.arguments["message"]});
              break;
          }
          return null;
        });
        await _channel.invokeMethod("download");
        return null;

      case "generate":
        final map = args as Map;
        final result = await _channel.invokeMethod<Map>("generate", {
          "prompt": map["prompt"],
          "temperature": map["temperature"],
          "top_k": map["top_k"],
          "max_output_tokens": map["max_output_tokens"],
        });
        return {"text": result?["text"] ?? ""};

      default:
        throw UnimplementedError("Unknown AiCore method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
