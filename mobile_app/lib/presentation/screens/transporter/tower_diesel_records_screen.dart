import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/constants/api_constants.dart';
import '../../../domain/entities/fuel_record.dart';
import '../../providers/auth_provider.dart';
import '../../providers/transporter_provider.dart';

class TowerDieselRecordsScreen extends StatefulWidget {
  const TowerDieselRecordsScreen({super.key});

  @override
  State<TowerDieselRecordsScreen> createState() =>
      _TowerDieselRecordsScreenState();
}

class _TowerDieselRecordsScreenState extends State<TowerDieselRecordsScreen> {
  late DateTime _selectedMonth;
  DateTime? _selectedDay;
  late final TextEditingController _searchController;
  String _appliedQuery = '';

  @override
  void initState() {
    super.initState();
    _selectedMonth = DateTime(DateTime.now().year, DateTime.now().month, 1);
    _searchController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load() {
    return context.read<TransporterProvider>().loadTowerDieselRecords(
          month: _selectedDay == null ? _selectedMonth.month : null,
          year: _selectedDay == null ? _selectedMonth.year : null,
          fillDate: _selectedDay,
          query: _appliedQuery,
        );
  }

  Future<void> _pickMonth() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedMonth,
      firstDate: DateTime(DateTime.now().year - 2, 1, 1),
      lastDate: DateTime(DateTime.now().year + 1, 12, 31),
      helpText: 'Select Month',
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _selectedMonth = DateTime(picked.year, picked.month, 1);
      _selectedDay = null;
    });
    if (!mounted) {
      return;
    }
    await _load();
  }

  Future<void> _pickDay() async {
    final baseDate = _selectedDay ?? _selectedMonth;
    final picked = await showDatePicker(
      context: context,
      initialDate: baseDate,
      firstDate: DateTime(DateTime.now().year - 2, 1, 1),
      lastDate: DateTime(DateTime.now().year + 1, 12, 31),
      helpText: 'Select Day',
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _selectedDay = DateTime(picked.year, picked.month, picked.day);
      _selectedMonth = DateTime(picked.year, picked.month, 1);
    });
    if (!mounted) {
      return;
    }
    await _load();
  }

  Future<void> _clearDayFilter() async {
    if (_selectedDay == null) {
      return;
    }
    setState(() {
      _selectedDay = null;
    });
    await _load();
  }

  Future<void> _applySearch() async {
    FocusScope.of(context).unfocus();
    setState(() {
      _appliedQuery = _searchController.text.trim();
    });
    await _load();
  }

  Future<void> _clearSearch() async {
    if (_searchController.text.isEmpty && _appliedQuery.isEmpty) {
      return;
    }
    _searchController.clear();
    setState(() {
      _appliedQuery = '';
    });
    await _load();
  }

  Future<void> _downloadMonthlyTripSheetPdf({
    required bool includeFilledQuantity,
    bool includeReadings = false,
  }) async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Session expired. Please login again.')),
      );
      return;
    }

    final query = <String, String>{
      'month': _selectedMonth.month.toString(),
      'year': _selectedMonth.year.toString(),
      if (includeFilledQuantity) 'include_filled_quantity': 'true',
      if (includeReadings) 'include_readings': 'true',
    };
    final response = await _fetchPdfResponse(
      token: session.accessToken,
      query: query,
    );
    if (!mounted) {
      return;
    }
    if (response == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Unable to download PDF right now. Please try again later.',
          ),
        ),
      );
      return;
    }

    final filename =
        'tower-diesel-tripsheet-${_selectedMonth.month.toString().padLeft(2, '0')}-${_selectedMonth.year}${includeReadings ? '-readings' : ''}${includeFilledQuantity ? '-with-qty' : ''}.pdf';
    final file = XFile.fromData(
      response.bodyBytes,
      name: filename,
      mimeType: 'application/pdf',
    );
    await Share.shareXFiles(
      [file],
      text: 'Tower diesel trip sheet PDF',
      subject: filename,
    );
  }

  Future<void> _showPdfOptions() async {
    await showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        final provider = context.read<TransporterProvider>();
        final auth = context.read<AuthProvider>();
        final readingsEnabled = auth.transporterProfile?.dieselReadingsEnabled ??
            auth.session?.dieselReadingsEnabled ??
            false;
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Tower Diesel PDF',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                'Choose whether to print the diesel trip sheet with the filled quantity column.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.black54,
                    ),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: provider.loading
                      ? null
                      : () async {
                          Navigator.of(sheetContext).pop();
                          await _downloadMonthlyTripSheetPdf(
                            includeFilledQuantity: false,
                          );
                        },
                  icon: const Icon(Icons.picture_as_pdf_outlined),
                  label: const Text('Without Filled Quantity'),
                ),
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: provider.loading
                      ? null
                      : () async {
                          Navigator.of(sheetContext).pop();
                          await _downloadMonthlyTripSheetPdf(
                            includeFilledQuantity: true,
                          );
                        },
                  icon: const Icon(Icons.local_gas_station_outlined),
                  label: const Text('With Filled Quantity'),
                ),
              ),
              if (readingsEnabled) ...[
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: provider.loading
                        ? null
                        : () async {
                            Navigator.of(sheetContext).pop();
                            await _downloadMonthlyTripSheetPdf(
                              includeFilledQuantity: true,
                              includeReadings: true,
                            );
                          },
                    icon: const Icon(Icons.monitor_heart_outlined),
                    label: const Text('With Readings + Filled Qty'),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Future<http.Response?> _fetchPdfResponse({
    required String token,
    required Map<String, String> query,
  }) async {
    for (final uri in _pdfEndpointCandidates(query)) {
      final response = await http.get(
        uri,
        headers: {
          'Accept': '*/*',
          'Authorization': 'Bearer $token',
        },
      );
      if (_looksLikePdf(response)) {
        return response;
      }
      if (response.statusCode != 200) {
        continue;
      }
    }
    return null;
  }

  bool _looksLikePdf(http.Response response) {
    if (response.statusCode != 200 || response.bodyBytes.length < 5) {
      return false;
    }
    final contentType = (response.headers['content-type'] ?? '').toLowerCase();
    final bytes = response.bodyBytes;
    final hasPdfMagic = bytes[0] == 0x25 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x44 &&
        bytes[3] == 0x46 &&
        bytes[4] == 0x2D;
    return hasPdfMagic || contentType.contains('application/pdf');
  }

  List<Uri> _pdfEndpointCandidates(Map<String, String> query) {
    final normalizedBase = ApiConstants.baseUrl.endsWith('/')
        ? ApiConstants.baseUrl.substring(0, ApiConstants.baseUrl.length - 1)
        : ApiConstants.baseUrl;
    final baseUri = Uri.parse(normalizedBase);

    String normalizePath(String rawPath) {
      if (rawPath.isEmpty) {
        return '';
      }
      var value = rawPath;
      while (value.endsWith('/')) {
        value = value.substring(0, value.length - 1);
      }
      return value;
    }

    final configuredPath = normalizePath(baseUri.path);
    final pathOptions = <String>[];

    void addPathOption(String value) {
      if (!pathOptions.contains(value)) {
        pathOptions.add(value);
      }
    }

    if (configuredPath.isEmpty) {
      addPathOption('/api');
      addPathOption('');
    } else {
      addPathOption(configuredPath);
      if (configuredPath == '/api') {
        addPathOption('');
      } else {
        addPathOption('/api');
      }
    }

    final candidates = <Uri>[];
    void addCandidate(String pathBase, bool withTrailingSlash) {
      final suffix = withTrailingSlash
          ? '/diesel/tripsheet/pdf/'
          : '/diesel/tripsheet/pdf';
      final path = '${pathBase.isEmpty ? '' : pathBase}$suffix';
      final uri = baseUri
          .replace(path: path, query: null, fragment: null)
          .replace(queryParameters: query);
      if (!candidates.contains(uri)) {
        candidates.add(uri);
      }
    }

    for (final pathBase in pathOptions) {
      addCandidate(pathBase, false);
      addCandidate(pathBase, true);
    }
    return candidates;
  }

  Future<void> _deleteRecord(int recordId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Delete Entry'),
          content: const Text('Delete this tower diesel entry?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );
    if (confirmed != true) {
      return;
    }
    if (!mounted) {
      return;
    }
    final provider = context.read<TransporterProvider>();
    final ok = await provider.deleteTowerDieselRecord(
      recordId: recordId,
      month: _selectedDay == null ? _selectedMonth.month : null,
      year: _selectedDay == null ? _selectedMonth.year : null,
      fillDate: _selectedDay,
      query: _appliedQuery,
    );
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(ok
              ? 'Deleted successfully.'
              : provider.error ?? 'Delete failed.')),
    );
  }

  Map<String, String> _authHeaders() {
    final token = context.read<AuthProvider>().session?.accessToken;
    if (token == null || token.isEmpty) {
      return const {'Accept': '*/*'};
    }
    return {
      'Accept': '*/*',
      'Authorization': 'Bearer $token',
    };
  }

  Future<void> _shareLogbookPhoto({
    required String imageUrl,
    required String siteName,
    required String siteId,
  }) async {
    final token = context.read<AuthProvider>().session?.accessToken;
    if (token == null || token.isEmpty) {
      _showMessage('Session expired. Please login again.');
      return;
    }

    try {
      final response = await http.get(
        Uri.parse(imageUrl),
        headers: _authHeaders(),
      );
      if (response.statusCode != 200 || response.bodyBytes.isEmpty) {
        _showMessage('Unable to fetch logbook photo.');
        return;
      }

      final trimmedSiteName = siteName.trim().isEmpty ? 'Tower Site' : siteName.trim();
      final trimmedSiteId = siteId.trim().isEmpty ? 'N/A' : siteId.trim();
      final safeSiteId = trimmedSiteId.replaceAll(RegExp(r'[^a-zA-Z0-9]+'), '_');
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final filename = 'tower_logbook_${safeSiteId}_$timestamp.jpg';
      final contentType = (response.headers['content-type'] ?? '').toLowerCase();
      final mimeType = contentType.contains('png') ? 'image/png' : 'image/jpeg';

      final file = XFile.fromData(
        response.bodyBytes,
        name: filename,
        mimeType: mimeType,
      );
      await Share.shareXFiles(
        [file],
        subject: 'Tower Logbook',
        text: 'Site: $trimmedSiteName | ID: $trimmedSiteId',
      );
    } catch (_) {
      _showMessage('Unable to share logbook photo right now.');
    }
  }

  Future<void> _bulkShareSelectedDayLogbooks() async {
    final day = _selectedDay;
    if (day == null) {
      _showMessage('Select a day first to bulk share logbook photos.');
      return;
    }

    final token = context.read<AuthProvider>().session?.accessToken;
    if (token == null || token.isEmpty) {
      _showMessage('Session expired. Please login again.');
      return;
    }

    final provider = context.read<TransporterProvider>();
    final recordsForDay = provider.towerDieselRecords.where((item) {
      final date = item.effectiveDate.toLocal();
      return date.year == day.year && date.month == day.month && date.day == day.day;
    }).toList();

    final withPhotos = recordsForDay
        .where((item) => item.logbookPhotoUrl.trim().isNotEmpty)
        .toList();

    if (withPhotos.isEmpty) {
      _showMessage('No logbook photos available for ${_formatDate(day)}.');
      return;
    }

    if (!mounted) {
      return;
    }

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return const AlertDialog(
          content: Row(
            children: [
              SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              SizedBox(width: 12),
              Expanded(child: Text('Preparing logbook photos for sharing...')),
            ],
          ),
        );
      },
    );

    final tempDir = await getTemporaryDirectory();
    final files = <XFile>[];
    var failed = 0;

    for (final item in withPhotos) {
      final imageUrl = item.logbookPhotoUrl.trim();
      if (imageUrl.isEmpty) {
        continue;
      }
      try {
        final response = await http.get(
          Uri.parse(imageUrl),
          headers: _authHeaders(),
        );
        if (response.statusCode != 200 || response.bodyBytes.isEmpty) {
          failed += 1;
          continue;
        }

        final siteId = item.indusSiteId.trim().isEmpty ? 'N_A' : item.indusSiteId.trim();
        final safeSiteId = siteId.replaceAll(RegExp(r'[^a-zA-Z0-9]+'), '_');
        final contentType = (response.headers['content-type'] ?? '').toLowerCase();
        final ext = contentType.contains('png') ? 'png' : 'jpg';
        final filename =
            'tower_logbook_${_formatDate(day)}_${safeSiteId}_${item.id}.$ext';
        final path =
            '${tempDir.path}${Platform.pathSeparator}$filename';
        await File(path).writeAsBytes(response.bodyBytes);
        files.add(
          XFile(
            path,
            mimeType: contentType.contains('png') ? 'image/png' : 'image/jpeg',
          ),
        );
      } catch (_) {
        failed += 1;
      }
    }

    if (mounted) {
      Navigator.of(context).pop(); // close progress dialog
    }

    if (files.isEmpty) {
      _showMessage('Unable to fetch logbook photos for sharing.');
      return;
    }

    final caption = _buildBulkShareCaption(day, withPhotos, failed: failed);
    await Share.shareXFiles(
      files,
      subject: 'Tower Logbooks - ${_formatDate(day)}',
      text: caption,
    );

    if (failed > 0) {
      _showMessage('$failed logbook photos could not be downloaded.');
    }
  }

  String _buildBulkShareCaption(
    DateTime day,
    List<FuelRecord> records, {
    int failed = 0,
  }) {
    final header = 'Tower Diesel Logbook Photos - ${_formatDate(day)}';
    final lines = <String>[];
    for (var i = 0; i < records.length; i++) {
      final item = records[i];
      final siteName = item.siteName.trim().isEmpty ? 'Tower Site' : item.siteName.trim();
      final siteId = item.indusSiteId.trim().isEmpty ? 'N/A' : item.indusSiteId.trim();
      final qty = item.fuelFilled.toStringAsFixed(2);
      final vehicle = item.vehicleNumber.trim().isEmpty ? '-' : item.vehicleNumber.trim();
      final driver = item.driverName.trim().isEmpty ? '-' : item.driverName.trim();
      lines.add('${i + 1}) $vehicle | $driver | $siteName ($siteId) | $qty L');
    }

    final footer = failed > 0 ? '\n\nNote: $failed photos failed to download.' : '';
    return '$header\n\n${lines.join('\n')}$footer';
  }

  void _showMessage(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final dieselEnabled = context.select(
      (AuthProvider auth) => auth.session?.dieselTrackingEnabled ?? false,
    );

    if (!dieselEnabled) {
      return Scaffold(
        appBar: AppBar(title: const Text('Tower Diesel Records')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.lock_outline,
                  size: 56,
                  color: Color(0xFF0F766E),
                ),
                const SizedBox(height: 12),
                Text(
                  'Tower diesel module is disabled for this transporter. Enable it in the admin panel to access tower records.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
        ),
      );
    }

    final monthLabel =
        '${_monthName(_selectedMonth.month)} ${_selectedMonth.year}';
    final selectedDayLabel =
        _selectedDay == null ? null : _formatDate(_selectedDay!);
    final auth = context.watch<AuthProvider>();
    final readingsEnabled = auth.transporterProfile?.dieselReadingsEnabled ??
        auth.session?.dieselReadingsEnabled ??
        false;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tower Diesel Records'),
        actions: [
          IconButton(
            icon: const Icon(Icons.picture_as_pdf_outlined),
            onPressed: _showPdfOptions,
            tooltip: 'Print Monthly Trip Sheet',
          ),
          IconButton(
            icon: const Icon(Icons.calendar_month_outlined),
            onPressed: _pickMonth,
            tooltip: 'Select month',
          ),
          IconButton(
            icon: const Icon(Icons.event_outlined),
            onPressed: _pickDay,
            tooltip: 'Select day',
          ),
          if (_selectedDay != null)
            IconButton(
              icon: const Icon(Icons.share_outlined),
              onPressed: _bulkShareSelectedDayLogbooks,
              tooltip: 'Share day logbook photos',
            ),
        ],
      ),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          if (provider.loading && provider.towerDieselRecords.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }
          if (provider.error != null && provider.towerDieselRecords.isEmpty) {
            return Center(child: Text(provider.error!));
          }
          return RefreshIndicator(
            onRefresh: _load,
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        TextField(
                          controller: _searchController,
                          textInputAction: TextInputAction.search,
                          onChanged: (_) => setState(() {}),
                          onSubmitted: (_) => _applySearch(),
                          decoration: InputDecoration(
                            labelText: 'Search by site name or site ID',
                            prefixIcon: const Icon(Icons.search),
                            suffixIcon: _searchController.text.isNotEmpty ||
                                    _appliedQuery.isNotEmpty
                                ? IconButton(
                                    icon: const Icon(Icons.close),
                                    onPressed: _clearSearch,
                                  )
                                : null,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            FilledButton.icon(
                              onPressed: _applySearch,
                              icon: const Icon(Icons.search),
                              label: const Text('Search'),
                            ),
                            OutlinedButton.icon(
                              onPressed: _pickDay,
                              icon: const Icon(Icons.event_outlined),
                              label: Text(
                                selectedDayLabel == null
                                    ? 'Select day'
                                    : 'Day: $selectedDayLabel',
                              ),
                            ),
                            if (_selectedDay != null)
                              TextButton(
                                onPressed: _clearDayFilter,
                                child: const Text('Clear day'),
                              ),
                            Chip(
                              avatar: const Icon(Icons.calendar_month_outlined, size: 18),
                              label: Text('Month: $monthLabel'),
                            ),
                            if (_appliedQuery.isNotEmpty)
                              Chip(
                                avatar: const Icon(Icons.filter_alt_outlined, size: 18),
                                label: Text('Query: $_appliedQuery'),
                              ),
                          ],
                        ),
                        if (provider.loading && provider.towerDieselRecords.isNotEmpty)
                          const Padding(
                            padding: EdgeInsets.only(top: 10),
                            child: LinearProgressIndicator(),
                          ),
                      ],
                    ),
                  ),
                ),
                if (provider.towerDieselRecords.isEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 48),
                    child: Center(
                      child: Text(
                        _selectedDay != null
                            ? 'No tower diesel records for ${_formatDate(_selectedDay!)}.'
                            : 'No tower diesel records in $monthLabel.',
                      ),
                    ),
                  )
                else
                  ...provider.towerDieselRecords.map((item) {
                    final date = item.effectiveDate.toLocal();
                    final piuLabel = item.piuReading == null
                        ? '-'
                        : item.piuReading!.toStringAsFixed(2);
                    final dgHmrLabel =
                        item.dgHmr == null ? '-' : item.dgHmr!.toStringAsFixed(2);
                    final openingStockLabel = item.openingStock == null
                        ? '-'
                        : item.openingStock!.toStringAsFixed(2);
                    return Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '${item.vehicleNumber} - ${item.siteName.isEmpty ? 'Tower Diesel' : item.siteName}',
                                    style: Theme.of(context).textTheme.titleMedium,
                                  ),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.delete_outline),
                                  onPressed: () => _deleteRecord(item.id),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Date: ${_formatDate(date)} | Fuel: ${item.fuelFilled.toStringAsFixed(2)} L',
                            ),
                            if (item.driverName.trim().isNotEmpty)
                              Text('Filled by: ${item.driverName}'),
                            Text(
                              'Start KM: ${item.startKm ?? 0} | End KM: ${item.endKm ?? 0} | Run KM: ${item.runKm}',
                            ),
                            if (readingsEnabled)
                              Text(
                                'PIU: $piuLabel | DG HMR: $dgHmrLabel | Opening Stock: $openingStockLabel',
                              ),
                            if (item.indusSiteId.isNotEmpty)
                              Text('Indus Site ID: ${item.indusSiteId}'),
                            if (item.logbookPhotoUrl.isNotEmpty)
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  TextButton.icon(
                                    onPressed: () => _openPhoto(item.logbookPhotoUrl),
                                    icon: const Icon(Icons.photo_outlined),
                                    label: const Text('View Logbook'),
                                  ),
                                  TextButton.icon(
                                    onPressed: () => _shareLogbookPhoto(
                                      imageUrl: item.logbookPhotoUrl,
                                      siteName: item.siteName,
                                      siteId: item.indusSiteId,
                                    ),
                                    icon: const Icon(Icons.share_outlined),
                                    label: const Text('Share Logbook'),
                                  ),
                                ],
                              ),
                          ],
                        ),
                      ),
                    );
                  }),
              ],
            ),
          );
        },
      ),
    );
  }

  String _formatDate(DateTime date) {
    final dd = date.day.toString().padLeft(2, '0');
    final mm = date.month.toString().padLeft(2, '0');
    return '$dd-$mm-${date.year}';
  }

  String _monthName(int month) {
    const names = <String>[
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    return names[month - 1];
  }

  void _openPhoto(String imageUrl) {
    final headers = _authHeaders();
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return Dialog(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420, maxHeight: 620),
            child: Column(
              children: [
                ListTile(
                  title: const Text('Logbook Photo'),
                  trailing: IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(dialogContext),
                  ),
                ),
                const Divider(height: 1),
                Expanded(
                  child: InteractiveViewer(
                    child: Image.network(
                      imageUrl,
                      fit: BoxFit.contain,
                      headers: headers,
                      errorBuilder: (_, __, ___) =>
                          const Center(child: Text('Unable to load logbook photo')),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
