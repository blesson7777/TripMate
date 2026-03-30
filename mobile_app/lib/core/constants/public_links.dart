import 'api_constants.dart';

class PublicLinks {
  PublicLinks._();

  static Uri get privacyPolicy =>
      Uri.parse(ApiConstants.baseUrl).resolve('/privacy-policy/');

  static Uri get accountDeletion =>
      Uri.parse(ApiConstants.baseUrl).resolve('/account-deletion/');
}
