final RegExp _emailPattern = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$');
final RegExp _indianLicensePattern = RegExp(r'^[A-Z]{2}\d{2}\d{4}\d{7}$');

String? validateEmailAddress(String? value) {
  final text = value?.trim() ?? '';
  if (text.isEmpty) {
    return 'Email is required';
  }
  if (!_emailPattern.hasMatch(text)) {
    return 'Enter a valid email address';
  }
  return null;
}

String normalizeIndianLicenseNumber(String value) {
  return value.toUpperCase().replaceAll(RegExp(r'[\s/-]+'), '');
}

String? validateIndianLicenseNumber(String? value) {
  final normalized = normalizeIndianLicenseNumber(value ?? '');
  if (normalized.isEmpty) {
    return 'License number is required';
  }
  if (!_indianLicensePattern.hasMatch(normalized)) {
    return 'Enter a valid Indian license number';
  }
  return null;
}
