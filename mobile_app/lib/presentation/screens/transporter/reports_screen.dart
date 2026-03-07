import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/constants/api_constants.dart';
import '../../providers/auth_provider.dart';
import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  final _monthController = TextEditingController();
  final _yearController = TextEditingController();
  int? _selectedVehicleId;
  int? _selectedServiceId;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _monthController.text = now.month.toString();
    _yearController.text = now.year.toString();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TransporterProvider>().loadDashboardData();
    });
  }

  @override
  void dispose() {
    _monthController.dispose();
    _yearController.dispose();
    super.dispose();
  }

  Future<void> _loadReport() async {
    final month = int.tryParse(_monthController.text.trim());
    final year = int.tryParse(_yearController.text.trim());

    if (month == null || year == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Month and year must be valid numbers.')),
      );
      return;
    }

    await context.read<TransporterProvider>().loadMonthlyReport(
          month: month,
          year: year,
          vehicleId: _selectedVehicleId,
          serviceId: _selectedServiceId,
        );
  }

  Future<void> _downloadPdf({required bool withHeader}) async {
    final month = int.tryParse(_monthController.text.trim());
    final year = int.tryParse(_yearController.text.trim());
    if (month == null || year == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Month and year must be valid numbers.')),
      );
      return;
    }

    final session = context.read<AuthProvider>().session;
    if (session == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Session expired. Please login again.')),
      );
      return;
    }

    final query = <String, String>{
      'month': month.toString(),
      'year': year.toString(),
      'layout': withHeader ? 'full' : 'compact',
      if (_selectedVehicleId != null)
        'vehicle_id': _selectedVehicleId.toString(),
      if (_selectedServiceId != null)
        'service_id': _selectedServiceId.toString(),
    };

    try {
      final response = await _fetchPdfResponse(
        token: session.accessToken,
        query: query,
      );
      if (response == null) {
        if (!mounted) {
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Server returned HTML or invalid PDF. Check API deployment and base URL.',
            ),
          ),
        );
        return;
      }

      final disposition = response.headers['content-disposition'] ?? '';
      final filenameMatch =
          RegExp(r'filename=\"?([^\";]+)\"?').firstMatch(disposition);
      final filename = filenameMatch?.group(1) ??
          'trip-sheet-${month.toString().padLeft(2, '0')}-$year-${withHeader ? "full" : "compact"}.pdf';

      final file = XFile.fromData(
        response.bodyBytes,
        name: filename,
        mimeType: 'application/pdf',
      );
      await Share.shareXFiles(
        [file],
        text: 'Trip sheet PDF',
        subject: filename,
      );
    } catch (_) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Failed to download PDF. Please retry.')),
      );
    }
  }

  Future<void> _downloadDieselTripSheetPdf({
    required bool includeFilledQuantity,
  }) async {
    final month = int.tryParse(_monthController.text.trim());
    final year = int.tryParse(_yearController.text.trim());
    if (month == null || year == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Month and year must be valid numbers.')),
      );
      return;
    }

    final session = context.read<AuthProvider>().session;
    if (session == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Session expired. Please login again.')),
      );
      return;
    }

    final query = <String, String>{
      'month': month.toString(),
      'year': year.toString(),
      if (includeFilledQuantity) 'include_filled_quantity': 'true',
    };

    try {
      final response = await _fetchDieselPdfResponse(
        token: session.accessToken,
        query: query,
      );
      if (response == null) {
        if (!mounted) {
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Server returned HTML or invalid diesel PDF. Check API deployment.',
            ),
          ),
        );
        return;
      }

      final filename =
          'diesel-fill-trip-sheet-${month.toString().padLeft(2, '0')}-$year${includeFilledQuantity ? '-with-qty' : ''}.pdf';
      final file = XFile.fromData(
        response.bodyBytes,
        name: filename,
        mimeType: 'application/pdf',
      );
      await Share.shareXFiles(
        [file],
        text: 'Diesel fill trip sheet PDF',
        subject: filename,
      );
    } catch (_) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Failed to download diesel trip sheet PDF.'),
        ),
      );
    }
  }

  Future<void> _showDieselPdfOptions() async {
    await showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        final provider = context.read<TransporterProvider>();
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
                'Diesel Fill PDF',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                'Choose whether to print the diesel fill sheet with the filled quantity column.',
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
                          await _downloadDieselTripSheetPdf(
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
                          await _downloadDieselTripSheetPdf(
                            includeFilledQuantity: true,
                          );
                        },
                  icon: const Icon(Icons.local_gas_station_outlined),
                  label: const Text('With Filled Quantity'),
                ),
              ),
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

  Future<http.Response?> _fetchDieselPdfResponse({
    required String token,
    required Map<String, String> query,
  }) async {
    for (final uri in _dieselPdfEndpointCandidates(query)) {
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
    final isPdfContentType = contentType.contains('application/pdf');
    return hasPdfMagic || isPdfContentType;
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
          ? '/reports/monthly/pdf/'
          : '/reports/monthly/pdf';
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

  List<Uri> _dieselPdfEndpointCandidates(Map<String, String> query) {
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

  Future<void> _openAddServiceSheet() async {
    final formKey = GlobalKey<FormState>();
    final nameController = TextEditingController();
    final descriptionController = TextEditingController();

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
          ),
          child: Container(
            decoration: const BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            ),
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Add Service',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: nameController,
                    decoration: const InputDecoration(
                      labelText: 'Service Name',
                      prefixIcon: Icon(Icons.miscellaneous_services_outlined),
                    ),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Service name is required';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: descriptionController,
                    decoration: const InputDecoration(
                      labelText: 'Description (optional)',
                      prefixIcon: Icon(Icons.description_outlined),
                    ),
                    maxLines: 2,
                  ),
                  const SizedBox(height: 14),
                  Consumer<TransporterProvider>(
                    builder: (context, provider, _) {
                      return FilledButton.icon(
                        onPressed: provider.loading
                            ? null
                            : () async {
                                if (!formKey.currentState!.validate()) {
                                  return;
                                }
                                final success = await context
                                    .read<TransporterProvider>()
                                    .addService(
                                      name: nameController.text.trim(),
                                      description:
                                          descriptionController.text.trim(),
                                      isActive: true,
                                    );
                                if (!context.mounted) {
                                  return;
                                }
                                if (!success) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        context
                                                .read<TransporterProvider>()
                                                .error ??
                                            'Unable to add service',
                                      ),
                                    ),
                                  );
                                  return;
                                }
                                Navigator.pop(context);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                      'Service added successfully',
                                    ),
                                  ),
                                );
                              },
                        icon: provider.loading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.add_rounded),
                        label: const Text('Add Service'),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _shareReport() async {
    final report = context.read<TransporterProvider>().monthlyReport;
    if (report == null || report.rows.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Generate a report before sharing.')),
      );
      return;
    }

    final buffer = StringBuffer();
    buffer.writeln('TripMate Service-wise Trip Sheet');
    buffer.writeln('Month: ${report.month} / ${report.year}');
    if (report.serviceName != null && report.serviceName!.trim().isNotEmpty) {
      buffer.writeln('Service: ${report.serviceName}');
    }
    buffer.writeln(
      'SlNo | Date | Vehicle | Service | Opening | Closing | Total | Purpose',
    );
    for (final row in report.rows) {
      final date = row.date.toLocal().toString().split(' ').first;
      buffer.writeln(
        '${row.slNo} | $date | ${row.vehicleNumber} | ${row.serviceName} | '
        '${row.openingKm} | ${row.closingKm} | ${row.totalRunKm} | ${row.purpose}',
      );
    }
    buffer.writeln(
        'Total days: ${report.totalDays}, Total KM: ${report.totalKm}');

    await Share.share(buffer.toString(), subject: 'Service-wise Trip Sheet');
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final dieselEnabled = context.select(
      (AuthProvider auth) => auth.session?.dieselTrackingEnabled ?? false,
    );

    return Scaffold(
      appBar: AppBar(title: const Text('Monthly Trip Sheet')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFEAF3F2), Color(0xFFF8EFE4)],
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Consumer<TransporterProvider>(
            builder: (context, provider, _) {
              final report = provider.monthlyReport;
              final vehicles = provider.vehicles;
              final services = provider.services;

              return Column(
                children: [
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 120),
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: TextField(
                                    controller: _monthController,
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                      labelText: 'Month',
                                      prefixIcon:
                                          Icon(Icons.calendar_today_outlined),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: TextField(
                                    controller: _yearController,
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                      labelText: 'Year',
                                      prefixIcon:
                                          Icon(Icons.date_range_outlined),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            DropdownButtonFormField<int?>(
                              initialValue: _selectedVehicleId,
                              decoration: const InputDecoration(
                                labelText: 'Vehicle (optional)',
                                prefixIcon: Icon(Icons.local_shipping_outlined),
                              ),
                              items: [
                                const DropdownMenuItem<int?>(
                                  value: null,
                                  child: Text('All Vehicles'),
                                ),
                                ...vehicles.map(
                                  (vehicle) => DropdownMenuItem<int?>(
                                    value: vehicle.id,
                                    child: Text(vehicle.vehicleNumber),
                                  ),
                                ),
                              ],
                              onChanged: (value) {
                                setState(() {
                                  _selectedVehicleId = value;
                                });
                              },
                            ),
                            const SizedBox(height: 10),
                            DropdownButtonFormField<int?>(
                              initialValue: _selectedServiceId,
                              decoration: const InputDecoration(
                                labelText: 'Service (optional)',
                                prefixIcon:
                                    Icon(Icons.miscellaneous_services_outlined),
                              ),
                              items: [
                                const DropdownMenuItem<int?>(
                                  value: null,
                                  child: Text('All Services'),
                                ),
                                ...services.map(
                                  (service) => DropdownMenuItem<int?>(
                                    value: service.id,
                                    child: Text(service.name),
                                  ),
                                ),
                              ],
                              onChanged: (value) {
                                setState(() {
                                  _selectedServiceId = value;
                                });
                              },
                            ),
                            const SizedBox(height: 10),
                            Row(
                              children: [
                                Expanded(
                                  child: Container(
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(16),
                                      gradient: const LinearGradient(
                                        colors: [
                                          Color(0xFF0A6B6F),
                                          Color(0xFF198288),
                                        ],
                                      ),
                                    ),
                                    child: FilledButton.icon(
                                      onPressed:
                                          provider.loading ? null : _loadReport,
                                      style: FilledButton.styleFrom(
                                        backgroundColor: Colors.transparent,
                                        shadowColor: Colors.transparent,
                                      ),
                                      icon: provider.loading
                                          ? const SizedBox(
                                              width: 18,
                                              height: 18,
                                              child: CircularProgressIndicator(
                                                strokeWidth: 2,
                                                color: Colors.white,
                                              ),
                                            )
                                          : const Icon(
                                              Icons.analytics_outlined),
                                      label: Text(provider.loading
                                          ? 'Generating...'
                                          : 'Generate Report'),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                OutlinedButton.icon(
                                  onPressed: _openAddServiceSheet,
                                  icon: const Icon(Icons.add_box_outlined),
                                  label: const Text('Add Service'),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  if (provider.error != null)
                    Text(provider.error!,
                        style: TextStyle(color: colors.error)),
                  if (report != null) ...[
                    StaggeredEntrance(
                      delay: const Duration(milliseconds: 200),
                      child: Card(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 12,
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: _ReportSummaryChip(
                                  icon: Icons.event_note_outlined,
                                  label: 'Total Days',
                                  value: '${report.totalDays}',
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: _ReportSummaryChip(
                                  icon: Icons.speed_outlined,
                                  label: 'Total KM',
                                  value: '${report.totalKm}',
                                ),
                              ),
                              const SizedBox(width: 10),
                              OutlinedButton.icon(
                                onPressed: _shareReport,
                                icon: const Icon(Icons.share_outlined),
                                label: const Text('Share'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    StaggeredEntrance(
                      delay: const Duration(milliseconds: 230),
                      child: Card(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 10,
                          ),
                          child: Wrap(
                            spacing: 10,
                            runSpacing: 8,
                            children: [
                              FilledButton.icon(
                                onPressed: provider.loading
                                    ? null
                                    : () => _downloadPdf(withHeader: true),
                                icon: const Icon(Icons.picture_as_pdf_outlined),
                                label: const Text('PDF Full (Header + Sign)'),
                              ),
                              OutlinedButton.icon(
                                onPressed: provider.loading
                                    ? null
                                    : () => _downloadPdf(withHeader: false),
                                icon: const Icon(Icons.grid_view_rounded),
                                label: const Text('PDF Data Only'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Expanded(
                      child: ListView.builder(
                        itemCount: report.rows.length,
                        itemBuilder: (context, index) {
                          final row = report.rows[index];
                          return StaggeredEntrance(
                            delay: Duration(milliseconds: 45 * index),
                            child: Card(
                              margin: const EdgeInsets.only(bottom: 8),
                              child: ListTile(
                                leading: Container(
                                  width: 36,
                                  height: 36,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF0A6B6F)
                                        .withValues(alpha: 0.14),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Center(
                                    child: Text(
                                      row.slNo.toString(),
                                      style: const TextStyle(
                                        color: Color(0xFF0A6B6F),
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ),
                                ),
                                title: Text(row.date
                                    .toLocal()
                                    .toString()
                                    .split(' ')
                                    .first),
                                subtitle: Text(
                                  '${row.vehicleNumber} | ${row.serviceName}\n'
                                  'Open: ${row.openingKm} | Close: ${row.closingKm} | Total: ${row.totalRunKm}\n'
                                  'Purpose: ${row.purpose}',
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                  if (dieselEnabled) ...[
                    const SizedBox(height: 10),
                    StaggeredEntrance(
                      delay: const Duration(milliseconds: 260),
                      child: Card(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 14,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Diesel Fill Trip Sheet',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w700),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                'Generate the monthly diesel fill PDF with site ID, site name, KM and signature footer.',
                                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                      color: Colors.black.withValues(alpha: 0.68),
                                    ),
                              ),
                              const SizedBox(height: 12),
                              FilledButton.icon(
                                onPressed: provider.loading
                                    ? null
                                    : _showDieselPdfOptions,
                                icon: const Icon(Icons.local_gas_station_outlined),
                                label: const Text('Download Diesel Fill PDF'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _ReportSummaryChip extends StatelessWidget {
  const _ReportSummaryChip({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFF2F8F7),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        child: Row(
          children: [
            Icon(icon, size: 20, color: const Color(0xFF0A6B6F)),
            const SizedBox(width: 6),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    value,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  Text(
                    label,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.black.withValues(alpha: 0.65),
                        ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
