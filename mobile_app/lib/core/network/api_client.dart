import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode, this.debugMessage});

  final String message;
  final int? statusCode;
  final String? debugMessage;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.baseUrl}) {
    _candidateBaseUrls = _buildCandidateBaseUrls(baseUrl);
    _activeBaseUrl = _candidateBaseUrls.first;
  }

  final String baseUrl;
  final http.Client _client = http.Client();
  late final List<String> _candidateBaseUrls;
  late String _activeBaseUrl;
  String? _accessToken;
  Future<bool> Function()? _refreshSessionHandler;
  Future<void> Function()? _authFailureHandler;
  Future<bool>? _refreshFuture;
  final StreamController<void> _authFailureEvents =
      StreamController<void>.broadcast();

  Stream<void> get authFailureEvents => _authFailureEvents.stream;

  void setAccessToken(String? token) {
    _accessToken = token;
  }

  void setAuthHandlers({
    Future<bool> Function()? onRefreshSession,
    Future<void> Function()? onAuthFailure,
  }) {
    _refreshSessionHandler = onRefreshSession;
    _authFailureHandler = onAuthFailure;
  }

  Future<dynamic> get(
    String endpoint, {
    Map<String, String>? query,
    bool includeAuth = true,
    bool allowAuthRetry = true,
  }) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint, query: query);
      final response = await _client
          .get(uri, headers: _headers(includeAuth: includeAuth))
          .timeout(const Duration(seconds: 20));
      return _decodeResponse(response);
    }, allowAuthRetry: allowAuthRetry);
  }

  Future<dynamic> post(
    String endpoint, {
    Map<String, dynamic>? body,
    bool includeAuth = true,
    bool allowAuthRetry = true,
  }) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint);
      final response = await _client
          .post(
            uri,
            headers: _headers(contentType: true, includeAuth: includeAuth),
            body: jsonEncode(body ?? <String, dynamic>{}),
          )
          .timeout(const Duration(seconds: 20));
      return _decodeResponse(response);
    }, allowAuthRetry: allowAuthRetry);
  }

  Future<dynamic> patch(
    String endpoint, {
    Map<String, dynamic>? body,
    bool includeAuth = true,
    bool allowAuthRetry = true,
  }) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint);
      final response = await _client
          .patch(
            uri,
            headers: _headers(contentType: true, includeAuth: includeAuth),
            body: jsonEncode(body ?? <String, dynamic>{}),
          )
          .timeout(const Duration(seconds: 20));
      return _decodeResponse(response);
    }, allowAuthRetry: allowAuthRetry);
  }

  Future<dynamic> delete(
    String endpoint, {
    Map<String, String>? query,
    bool includeAuth = true,
    bool allowAuthRetry = true,
  }) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint, query: query);
      final response = await _client
          .delete(uri, headers: _headers(includeAuth: includeAuth))
          .timeout(const Duration(seconds: 20));
      return _decodeResponse(response);
    }, allowAuthRetry: allowAuthRetry);
  }

  Future<dynamic> postMultipart(
    String endpoint, {
    Map<String, String>? fields,
    Map<String, File?>? files,
    bool includeAuth = true,
    bool allowAuthRetry = true,
  }) async {
    return _requestWithFallback((base) async {
      final uri = _buildUri(base, endpoint);
      final request = http.MultipartRequest('POST', uri);
      request.headers.addAll(_headers(includeAuth: includeAuth));

      if (fields != null) {
        request.fields.addAll(fields);
      }

      if (files != null) {
        final multipartFiles = await Future.wait(
          files.entries
              .where((entry) => entry.value != null)
              .map(
                (entry) => http.MultipartFile.fromPath(
                  entry.key,
                  entry.value!.path,
                ),
              ),
        );
        request.files.addAll(multipartFiles);
      }

      final streamed = await _client
          .send(request)
          .timeout(const Duration(seconds: 30));
      final response = await http.Response.fromStream(streamed);
      return _decodeResponse(response);
    }, allowAuthRetry: allowAuthRetry);
  }

  Map<String, String> _headers({
    bool contentType = false,
    bool includeAuth = true,
  }) {
    final headers = <String, String>{
      'Accept': 'application/json',
    };

    if (contentType) {
      headers['Content-Type'] = 'application/json';
    }

    if (includeAuth && _accessToken != null && _accessToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $_accessToken';
    }

    return headers;
  }

  dynamic _decodeResponse(http.Response response) {
    dynamic decoded;
    final contentType = response.headers['content-type']?.toLowerCase() ?? '';
    final isJson = contentType.contains('application/json');
    if (response.body.isNotEmpty && isJson) {
      try {
        decoded = jsonDecode(response.body);
      } on FormatException {
        decoded = null;
      }
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final debugMessage = decoded is Map<String, dynamic>
          ? _extractJsonErrorMessage(decoded)
          : _extractNonJsonError(response);
      final message = _buildUserMessage(
        statusCode: response.statusCode,
        decoded: decoded,
        debugMessage: debugMessage,
      );
      throw ApiException(
        message,
        statusCode: response.statusCode,
        debugMessage: debugMessage,
      );
    }

    if (decoded == null) {
      throw ApiException(
        'Unexpected response from server. Please try again.',
        statusCode: response.statusCode,
        debugMessage:
            'Server returned non-JSON success response (HTTP ${response.statusCode}).',
      );
    }

    return decoded;
  }

  String _buildUserMessage({
    required int statusCode,
    required dynamic decoded,
    required String debugMessage,
  }) {
    if (statusCode == 401) {
      return 'Session expired. Please login again.';
    }

    if (statusCode >= 500) {
      return 'Server error. Please try again later.';
    }

    if (decoded is Map<String, dynamic>) {
      final extracted = _extractJsonErrorMessage(decoded).trim();
      if (extracted.isNotEmpty && extracted.length <= 180) {
        return extracted;
      }
    }

    final normalized = debugMessage.toLowerCase();
    if (normalized.contains('html page') ||
        normalized.contains('<html') ||
        normalized.contains('<!doctype')) {
      return 'Server error. Please try again later.';
    }

    if (statusCode == 403) {
      return 'You do not have permission to perform this action.';
    }

    if (statusCode == 404) {
      return 'Requested resource not found.';
    }

    return 'Request failed. Please try again.';
  }

  String _extractNonJsonError(http.Response response) {
    final body = response.body.trim();
    if (body.isEmpty) {
      return 'HTTP ${response.statusCode}: Empty response from server.';
    }

    if (body.startsWith('<!doctype html') ||
        body.startsWith('<html') ||
        body.contains('<title>')) {
      return 'HTTP ${response.statusCode}: Server returned HTML page instead of JSON. '
          'Check server routing and deployment.';
    }

    final snippet = body.length > 240 ? '${body.substring(0, 240)}...' : body;
    return 'HTTP ${response.statusCode}: $snippet';
  }

  String _extractJsonErrorMessage(Map<String, dynamic> decoded) {
    String firstFrom(dynamic value) {
      if (value == null) {
        return '';
      }
      if (value is String) {
        return value;
      }
      if (value is List && value.isNotEmpty) {
        return value.first.toString();
      }
      return value.toString();
    }

    final detail = firstFrom(decoded['detail']);
    if (detail.isNotEmpty) {
      return detail;
    }

    final nonField = firstFrom(decoded['non_field_errors']);
    if (nonField.isNotEmpty) {
      return nonField;
    }

    for (final entry in decoded.entries) {
      final text = firstFrom(entry.value);
      if (text.isNotEmpty) {
        return text;
      }
    }

    return decoded.toString();
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
    {
    bool allowAuthRetry = true,
  }) async {
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
      } on ApiException catch (exception) {
        final canRefresh = allowAuthRetry &&
            exception.statusCode == 401 &&
            (_accessToken?.isNotEmpty ?? false) &&
            _refreshSessionHandler != null;
        if (canRefresh) {
          final refreshed = await _attemptRefresh();
          if (refreshed) {
            return _requestWithFallback(request, allowAuthRetry: false);
          }
          await _handleAuthFailure();
        }
        rethrow;
      } on TimeoutException {
        continue;
      } on HandshakeException {
        continue;
      } on SocketException {
        continue;
      } on HttpException {
        continue;
      } on http.ClientException {
        continue;
      } on FormatException {
        throw ApiException('Invalid response from server.');
      }
    }

    throw ApiException(
      'Unable to connect. Please check your internet connection and try again.',
      debugMessage: _connectionHint(attempted),
    );
  }

  Future<bool> _attemptRefresh() {
    final handler = _refreshSessionHandler;
    if (handler == null) {
      return Future.value(false);
    }
    final existing = _refreshFuture;
    if (existing != null) {
      return existing;
    }
    final future = handler().catchError((_) => false).whenComplete(() {
      _refreshFuture = null;
    });
    _refreshFuture = future;
    return future;
  }

  Future<void> _handleAuthFailure() async {
    final handler = _authFailureHandler;
    if (handler != null) {
      try {
        await handler();
      } catch (_) {
        // Keep auth cleanup best-effort.
      }
    }
    try {
      _authFailureEvents.add(null);
    } catch (_) {
      // Keep event dispatch best-effort.
    }
  }

  String _connectionHint(List<String> attempted) {
    final attempts = attempted.join(', ');
    return 'Cannot reach API. Tried: $attempts.';
  }
}
