import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class TripMateTheme {
  TripMateTheme._();

  static ThemeData transporterTheme() {
    const colorScheme = ColorScheme(
      brightness: Brightness.light,
      primary: Color(0xFF0A6B6F),
      onPrimary: Colors.white,
      secondary: Color(0xFFE08D3C),
      onSecondary: Colors.white,
      error: Color(0xFFB00020),
      onError: Colors.white,
      surface: Color(0xFFF9F7F2),
      onSurface: Color(0xFF1B2228),
    );

    final base = ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: const Color(0xFFF2EFE8),
    );

    return base.copyWith(
      textTheme: GoogleFonts.manropeTextTheme(base.textTheme).copyWith(
        headlineLarge: GoogleFonts.sora(
          fontSize: 34,
          fontWeight: FontWeight.w700,
          color: colorScheme.onSurface,
        ),
        headlineMedium: GoogleFonts.sora(
          fontSize: 28,
          fontWeight: FontWeight.w700,
          color: colorScheme.onSurface,
        ),
        titleLarge: GoogleFonts.sora(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          color: colorScheme.onSurface,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(22),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(
            color: colorScheme.primary.withValues(alpha: 0.16),
            width: 1,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(
            color: colorScheme.primary,
            width: 1.5,
          ),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: GoogleFonts.sora(
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        foregroundColor: colorScheme.onSurface,
        elevation: 0,
        titleTextStyle: GoogleFonts.sora(
          color: colorScheme.onSurface,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
