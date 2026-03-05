import 'dart:io';
import 'dart:math' as math;

import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

class OdometerScanResult {
  const OdometerScanResult({
    required this.value,
    required this.candidates,
    required this.rawText,
    required this.confidence,
    required this.fromKeywordContext,
  });

  final int? value;
  final List<int> candidates;
  final String rawText;
  final double confidence;
  final bool fromKeywordContext;
}

class OcrService {
  OcrService() : _textRecognizer = TextRecognizer(script: TextRecognitionScript.latin);

  final TextRecognizer _textRecognizer;

  Future<OdometerScanResult> analyzeOdometer(File imageFile) async {
    final inputImage = InputImage.fromFile(imageFile);
    final recognizedText = await _textRecognizer.processImage(inputImage);
    final rawText = recognizedText.text;
    final lines = rawText
        .split(RegExp(r'[\r\n]+'))
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList();

    final scoredCandidates = <_ScoredCandidate>[];
    for (var index = 0; index < lines.length; index++) {
      final line = lines[index];
      final numbers = _extractCandidates(line);
      if (numbers.isEmpty) {
        continue;
      }

      final lineHasKeyword = _containsOdometerKeyword(line);
      final previousHasKeyword =
          index > 0 ? _containsOdometerKeyword(lines[index - 1]) : false;
      final nextHasKeyword =
          index < lines.length - 1 ? _containsOdometerKeyword(lines[index + 1]) : false;

      for (final value in numbers) {
        var score = value.toString().length * 6;

        if (lineHasKeyword) {
          score += 35;
        } else if (previousHasKeyword || nextHasKeyword) {
          score += 18;
        }

        if (value >= 1000) {
          score += 10;
        } else if (value >= 100) {
          score += 4;
        }

        if (value > 9999999) {
          score -= 20;
        }

        scoredCandidates.add(
          _ScoredCandidate(
            value: value,
            score: score,
            fromKeywordContext: lineHasKeyword || previousHasKeyword || nextHasKeyword,
          ),
        );
      }
    }

    if (scoredCandidates.isEmpty) {
      return OdometerScanResult(
        value: null,
        candidates: [],
        rawText: rawText,
        confidence: 0,
        fromKeywordContext: false,
      );
    }

    scoredCandidates.sort((a, b) => b.score.compareTo(a.score));
    final best = scoredCandidates.first;
    final uniqueValues = <int>{
      for (final candidate in scoredCandidates) candidate.value,
    }.toList();
    uniqueValues.sort((a, b) => b.compareTo(a));

    final confidence = math.min(0.99, math.max(0.2, best.score / 100));
    return OdometerScanResult(
      value: best.value,
      candidates: uniqueValues,
      rawText: rawText,
      confidence: confidence,
      fromKeywordContext: best.fromKeywordContext,
    );
  }

  Future<int?> extractOdometerValue(File imageFile) async {
    final result = await analyzeOdometer(imageFile);
    return result.value;
  }

  void dispose() {
    _textRecognizer.close();
  }

  List<int> _extractCandidates(String text) {
    final result = <int>{};

    final compactPattern = RegExp(r'\d{3,8}');
    for (final match in compactPattern.allMatches(text)) {
      final value = int.tryParse(match.group(0) ?? '');
      if (value != null) {
        result.add(value);
      }
    }

    final spacedPattern = RegExp(r'\d[\d\s]{2,12}\d');
    for (final match in spacedPattern.allMatches(text)) {
      final digits = (match.group(0) ?? '').replaceAll(RegExp(r'\D'), '');
      if (digits.length < 3 || digits.length > 8) {
        continue;
      }
      final value = int.tryParse(digits);
      if (value != null) {
        result.add(value);
      }
    }

    return result.toList();
  }

  bool _containsOdometerKeyword(String text) {
    return RegExp(
      r'(odo|odometer|meter|km|kms|kilometer|kilometre)',
      caseSensitive: false,
    ).hasMatch(text);
  }
}

class _ScoredCandidate {
  const _ScoredCandidate({
    required this.value,
    required this.score,
    required this.fromKeywordContext,
  });

  final int value;
  final int score;
  final bool fromKeywordContext;
}
