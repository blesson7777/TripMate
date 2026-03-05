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
  ApiClient({required this.baseUrl}) {
    _candidateBaseUrls = _buildCandidateBaseUrls(baseUrl);
    _activeBaseUrl = _candidateBaseUrls.first;
  }

  final String baseUrl;
  late final List<String> _candidateBaseUrls;
  late String _activeBaseUrl;
  String? _accessToken;

  void setAccessToken(String? token) {
    _accessToken = token;
  }

  Future<dynamic> get(String endpoint, {Map<String, String>? query}) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint, query: query);
      final response = await http.get(uri, headers: _headers());
      return _decodeResponse(response);
    });
  }

  Future<dynamic> post(String endpoint, {Map<String, dynamic>? body}) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint);
      final response = await http.post(
        uri,
        headers: _headers(contentType: true),
        body: jsonEncode(body ?? <String, dynamic>{}),
      );
      return _decodeResponse(response);
    });
  }

  Future<dynamic> patch(String endpoint, {Map<String, dynamic>? body}) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint);
      final response = await http.patch(
        uri,
        headers: _headers(contentType: true),
        body: jsonEncode(body ?? <String, dynamic>{}),
      );
      return _decodeResponse(response);
    });
  }

  Future<dynamic> postMultipart(
    String endpoint, {
    Map<String, String>? fields,
    Map<String, File?>? files,
  }) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint);
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
          request.files
              .add(await http.MultipartFile.fromPath(entry.key, file.path));
        }
      }

      final streamed = await request.send();
      final response = await http.Response.fromStream(streamed);
      return _decodeResponse(response);
    });
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

  Uri _buildUri(
    String base,
    String endpoint, {
    Map<String, String>? query,
  }) {
    final normalizedBase = _normalizeBase(base);
    final normalizedEndpoint =
        endpoint.startsWith('/') ? endpoint : '/$endpoint';
    return Uri.parse('$normalizedBase$normalizedEndpoint').replace(
      queryParameters: query,
    );
  }

  List<String> _buildCandidateBaseUrls(String configuredBase) {
    final normalized = _normalizeBase(configuredBase);
    final uri = Uri.parse(normalized);
    final list = <String>[normalized];

    String withHost(String host) {
      return uri.replace(host: host).toString();
    }

    if (uri.host == '10.0.2.2') {
      list.add(withHost('127.0.0.1'));
      list.add(withHost('localhost'));
    } else if (uri.host == '127.0.0.1' || uri.host == 'localhost') {
      list.add(withHost('10.0.2.2'));
      if (uri.host == 'localhost') {
        list.add(withHost('127.0.0.1'));
      } else {
        list.add(withHost('localhost'));
      }
    }

    final deduped = <String>[];
    for (final item in list) {
      if (!deduped.contains(item)) {
        deduped.add(item);
      }
    }
    return deduped;
  }

  String _normalizeBase(String base) {
    if (base.endsWith('/')) {
      return base.substring(0, base.length - 1);
    }
    return base;
  }

  Future<dynamic> _requestWithFallback(
    Future<dynamic> Function(String base) request,
  ) async {
    final ordered = <String>[
      _activeBaseUrl,
      ..._candidateBaseUrls.where((value) => value != _activeBaseUrl),
    ];

    final attempted = <String>[];
    for (final candidate in ordered) {
      attempted.add(candidate);
      try {
        final result = await request(candidate);
        _activeBaseUrl = candidate;
        return result;
      } on SocketException {
        continue;
      } on http.ClientException {
        continue;
      } on FormatException {
        throw ApiException('Invalid response from server.');
      }
    }

    throw ApiException(_connectionHint(attempted));
  }

  String _connectionHint(List<String> attempted) {
    final attempts = attempted.join(', ');
    return 'Cannot reach API. Tried: $attempts. '
        'Ensure Django runs on 0.0.0.0:8000. '
        'For physical phone use adb reverse tcp:8000 tcp:8000, '
        'or pass --dart-define=API_BASE_URL=http://<YOUR_PC_IP>:8000/api.';
  }
}
