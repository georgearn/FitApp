import 'package:flet/flet.dart';

import 'aicore_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "aicore":
        return AiCoreService(control: control);
      default:
        return null;
    }
  }
}
