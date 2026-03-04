import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient {
  ApiClient({required this.baseUrl});

  final String baseUrl;
  String? _accessToken;

  void setAccessToken(String? token) {
    _accessToken = token;
  }

  Future<dynamic> get(String endpoint, {Map<String, String>? query}) async {
    final uri = Uri.parse('$baseUrl$endpoint').replace(queryParameters: query);
    final response = await http.get(uri, headers: _headers());
    return _decodeResponse(response);
  }

  Future<dynamic> post(String endpoint, {Map<String, dynamic>? body}) async {
    final uri = Uri.parse('$baseUrl$endpoint');
    final response = await http.post(
      uri,
      headers: _headers(contentType: true),
      body: jsonEncode(body ?? <String, dynamic>{}),
    );
    return _decodeResponse(response);
  }

  Future<dynamic> postMultipart(
    String endpoint, {
    Map<String, String>? fields,
    Map<String, File?>? files,
  }) async {
    final uri = Uri.parse('$baseUrl$endpoint');
    final request = http.MultipartRequest('POST', uri);
    request.headers.addAll(_headers());

    if (fields != null) {
      request.fields.addAll(fields);
    }

    if (files != null) {
      for (final entry in files.entries) {
        final file = entry.value;
        if (file == null) {
          continue;
        }
        request.files.add(await http.MultipartFile.fromPath(entry.key, file.path));
      }
    }

    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    return _decodeResponse(response);
  }

  Map<String, String> _headers({bool contentType = false}) {
    final headers = <String, String>{
      'Accept': 'application/json',
    };

    if (contentType) {
      headers['Content-Type'] = 'application/json';
    }

    if (_accessToken != null && _accessToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $_accessToken';
    }

    return headers;
  }

  dynamic _decodeResponse(http.Response response) {
    dynamic decoded;
    if (response.body.isNotEmpty) {
      decoded = jsonDecode(response.body);
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final message = decoded is Map<String, dynamic>
          ? decoded['detail']?.toString() ?? decoded.toString()
          : response.body;
      throw ApiException(message, statusCode: response.statusCode);
    }

    return decoded;
  }
}
