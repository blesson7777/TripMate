import 'dart:io';

import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

class OcrService {
  OcrService() : _textRecognizer = TextRecognizer(script: TextRecognitionScript.latin);

  final TextRecognizer _textRecognizer;

  Future<int?> extractOdometerValue(File imageFile) async {
    final inputImage = InputImage.fromFile(imageFile);
    final recognizedText = await _textRecognizer.processImage(inputImage);
    final text = recognizedText.text.replaceAll(',', ' ');

    final matches = RegExp(r'\d{2,7}').allMatches(text);
    if (matches.isEmpty) {
      return null;
    }

    final values = matches
        .map((match) => int.tryParse(match.group(0) ?? ''))
        .whereType<int>()
        .toList()
      ..sort((a, b) => b.compareTo(a));

    if (values.isEmpty) {
      return null;
    }

    return values.first;
  }

  void dispose() {
    _textRecognizer.close();
  }
}
