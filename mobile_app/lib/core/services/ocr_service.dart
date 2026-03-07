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
  static const int _preferredOdometerWindowKm = 100;
  static const int _fallbackOdometerWindowKm = 300;

  Future<OdometerScanResult> analyzeOdometer(
    File imageFile, {
    int? minimumValue,
  }) async {
    final inputImage = InputImage.fromFile(imageFile);
    final recognizedText = await _textRecognizer.processImage(inputImage);
    return analyzeOdometerText(
      recognizedText.text,
      minimumValue: minimumValue,
    );
  }

  OdometerScanResult analyzeOdometerText(
    String rawText, {
    int? minimumValue,
  }) {
    final lines = rawText
        .split(RegExp(r'[\r\n]+'))
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList();

    final scoredCandidates = <_ScoredCandidate>[];
    for (var index = 0; index < lines.length; index++) {
      final line = lines[index];
      final digitStrings = _extractCandidateStrings(line);
      if (digitStrings.isEmpty) {
        continue;
      }

      final lineHasKeyword = _containsOdometerKeyword(line);
      final previousHasKeyword =
          index > 0 ? _containsOdometerKeyword(lines[index - 1]) : false;
      final nextHasKeyword =
          index < lines.length - 1 ? _containsOdometerKeyword(lines[index + 1]) : false;
      final keywordContext =
          lineHasKeyword || previousHasKeyword || nextHasKeyword;

      for (final digits in digitStrings) {
        for (final candidate in _buildCandidatesForDigits(
          digits,
          minimumValue: minimumValue,
          allowPrefixCompletion: keywordContext,
        )) {
          final score = _scoreCandidate(
            value: candidate.value,
            minimumValue: minimumValue,
            fromKeywordContext: keywordContext,
            rawDigitLength: digits.length,
            prefixCompleted: candidate.prefixCompleted,
          );
          scoredCandidates.add(
            _ScoredCandidate(
              value: candidate.value,
              score: score,
              fromKeywordContext: keywordContext,
            ),
          );
        }
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
    final candidateScoreMap = <int, int>{};
    for (final candidate in scoredCandidates) {
      final currentScore = candidateScoreMap[candidate.value];
      if (currentScore == null || candidate.score > currentScore) {
        candidateScoreMap[candidate.value] = candidate.score;
      }
    }
    final uniqueValues = candidateScoreMap.keys.toList()
      ..sort((a, b) {
        final scoreCompare =
            (candidateScoreMap[b] ?? 0).compareTo(candidateScoreMap[a] ?? 0);
        if (scoreCompare != 0) {
          return scoreCompare;
        }
        return b.compareTo(a);
      });

    final confidence = math.min(0.99, math.max(0.2, best.score / 100));
    return OdometerScanResult(
      value: best.value,
      candidates: uniqueValues,
      rawText: rawText,
      confidence: confidence,
      fromKeywordContext: best.fromKeywordContext,
    );
  }

  Future<int?> extractOdometerValue(
    File imageFile, {
    int? minimumValue,
  }) async {
    final result = await analyzeOdometer(
      imageFile,
      minimumValue: minimumValue,
    );
    return result.value;
  }

  void dispose() {
    _textRecognizer.close();
  }

  List<String> _extractCandidateStrings(String text) {
    final result = <String>{};

    void collectMatches(RegExp pattern, {required bool allowSpaces}) {
      for (final match in pattern.allMatches(text)) {
        final raw = match.group(0) ?? '';
        if (!RegExp(r'\d').hasMatch(raw)) {
          continue;
        }
        final normalized = _normalizeNumericToken(raw, allowSpaces: allowSpaces);
        final digits = normalized.replaceAll(RegExp(r'\s+'), '');
        if (digits.length < 3 || digits.length > 8) {
          continue;
        }
        result.add(digits);
      }
    }

    collectMatches(
      RegExp(r'[0-9ODQILSBZG]{3,8}', caseSensitive: false),
      allowSpaces: false,
    );
    collectMatches(
      RegExp(r'[0-9ODQILSBZG][0-9ODQILSBZG\s]{2,12}[0-9ODQILSBZG]', caseSensitive: false),
      allowSpaces: true,
    );

    return result.toList();
  }

  String _normalizeNumericToken(String text, {required bool allowSpaces}) {
    final buffer = StringBuffer();
    for (final rune in text.runes) {
      final char = String.fromCharCode(rune);
      final upper = char.toUpperCase();
      if (RegExp(r'\d').hasMatch(char)) {
        buffer.write(char);
        continue;
      }
      if (allowSpaces && RegExp(r'\s').hasMatch(char)) {
        buffer.write(' ');
        continue;
      }
      switch (upper) {
        case 'O':
        case 'D':
        case 'Q':
          buffer.write('0');
          break;
        case 'I':
        case 'L':
        case '|':
          buffer.write('1');
          break;
        case 'S':
          buffer.write('5');
          break;
        case 'B':
          buffer.write('8');
          break;
        case 'G':
          buffer.write('6');
          break;
        case 'Z':
          buffer.write('2');
          break;
      }
    }
    return buffer.toString();
  }

  List<_DerivedCandidate> _buildCandidatesForDigits(
    String digits, {
    required int? minimumValue,
    required bool allowPrefixCompletion,
  }) {
    final candidates = <_DerivedCandidate>[];
    final parsed = int.tryParse(digits);
    if (parsed != null) {
      candidates.add(_DerivedCandidate(value: parsed, prefixCompleted: false));
    }

    if (minimumValue == null || !allowPrefixCompletion) {
      return candidates;
    }

    final minimumText = minimumValue.toString();
    final missingDigits = minimumText.length - digits.length;
    if (digits.length >= 4 && missingDigits >= 1 && missingDigits <= 2) {
      final completed = '${minimumText.substring(0, missingDigits)}$digits';
      final completedValue = int.tryParse(completed);
      if (completedValue != null) {
        candidates.add(
          _DerivedCandidate(value: completedValue, prefixCompleted: true),
        );
      }
    }

    return candidates;
  }

  int _scoreCandidate({
    required int value,
    required int? minimumValue,
    required bool fromKeywordContext,
    required int rawDigitLength,
    required bool prefixCompleted,
  }) {
    var score = rawDigitLength * 6;

    if (fromKeywordContext) {
      score += 40;
    } else {
      score += 4;
    }

    if (value >= 1000) {
      score += 10;
    } else if (value >= 100) {
      score += 4;
    }
    if (value >= 10000) {
      score += 8;
    }
    if (value >= 100000) {
      score += 10;
    }
    if (value > 9999999) {
      score -= 40;
    }

    if (prefixCompleted) {
      score -= 4;
      if (fromKeywordContext) {
        score += 6;
      }
    }

    if (minimumValue != null) {
      final delta = value - minimumValue;
      if (delta < 0) {
        score -= 240;
      } else if (delta <= 20) {
        score += 46;
      } else if (delta <= 50) {
        score += 34;
      } else if (delta <= _preferredOdometerWindowKm) {
        score += 22;
      } else if (delta <= 150) {
        score += 8;
      } else if (delta <= _fallbackOdometerWindowKm) {
        score -= 8;
      } else {
        score -= 70;
      }

      if (delta >= 0) {
        score -= (delta / 8).round();
      }

      if (value.toString().length == minimumValue.toString().length) {
        score += 10;
      }
    }

    return score;
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

class _DerivedCandidate {
  const _DerivedCandidate({
    required this.value,
    required this.prefixCompleted,
  });

  final int value;
  final bool prefixCompleted;
}
