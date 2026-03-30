import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/constants/api_constants.dart';
import '../../providers/auth_provider.dart';
import '../../providers/transporter_provider.dart';
import 'transporter_profile_screen.dart';

class VehicleBillScreen extends StatefulWidget {
  const VehicleBillScreen({super.key});

  @override
  State<VehicleBillScreen> createState() => _VehicleBillScreenState();
}

class _BillRecipient {
  const _BillRecipient({
    required this.id,
    required this.name,
    required this.address,
  });

  final int id;
  final String name;
  final String address;

  String get label => name.trim().isEmpty ? 'Recipient #$id' : name.trim();
}

class _SavedBill {
  const _SavedBill({
    required this.id,
    required this.billNo,
    required this.vehicleNumber,
    required this.serviceName,
    required this.totalAmount,
    required this.month,
    required this.year,
    required this.billDate,
    required this.createdAt,
  });

  final int id;
  final String billNo;
  final String vehicleNumber;
  final String serviceName;
  final String totalAmount;
  final int? month;
  final int? year;
  final DateTime? billDate;
  final DateTime? createdAt;

  String get periodLabel {
    if (month == null || year == null) {
      return '';
    }
    return '${month.toString().padLeft(2, '0')}/$year';
  }
}

class _VehicleBillScreenState extends State<VehicleBillScreen> {
  final _formKey = GlobalKey<FormState>();

  final _monthController = TextEditingController();
  final _yearController = TextEditingController();
  DateTime _billDate = DateTime.now();

  int? _selectedRecipientId;
  int? _selectedVehicleId;
  int? _selectedServiceId;

  final _serviceOverrideController = TextEditingController();
  final _baseAmountController = TextEditingController(text: '0');
  final _extraKmController = TextEditingController(text: '0');
  final _extraRateController = TextEditingController(text: '0');

  final _bankNameController = TextEditingController();
  final _bankBranchController = TextEditingController();
  final _bankAccountController = TextEditingController();
  final _bankIfscController = TextEditingController();

  bool _loading = false;
  List<_BillRecipient> _recipients = const [];
  List<_SavedBill> _bills = const [];

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _monthController.text = now.month.toString();
    _yearController.text = now.year.toString();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _bootstrap();
    });
  }

  @override
  void dispose() {
    _monthController.dispose();
    _yearController.dispose();
    _serviceOverrideController.dispose();
    _baseAmountController.dispose();
    _extraKmController.dispose();
    _extraRateController.dispose();
    _bankNameController.dispose();
    _bankBranchController.dispose();
    _bankAccountController.dispose();
    _bankIfscController.dispose();
    super.dispose();
  }

  String _normalizedBaseUrl() {
    var base = ApiConstants.baseUrl.trim();
    while (base.endsWith('/')) {
      base = base.substring(0, base.length - 1);
    }
    return base;
  }

  Uri _buildApiUri(String endpoint) {
    final base = _normalizedBaseUrl();
    final suffix = endpoint.startsWith('/') ? endpoint : '/$endpoint';
    return Uri.parse('$base$suffix');
  }

  String _errorFromResponse(http.Response response) {
    final contentType = (response.headers['content-type'] ?? '').toLowerCase();
    if (contentType.contains('application/json') && response.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          final detail = decoded['detail']?.toString();
          if (detail != null && detail.trim().isNotEmpty) {
            return detail.trim();
          }
        }
      } catch (_) {}
    }

    if (response.body.isNotEmpty) {
      final text = response.body.trim();
      final snippet = text.length > 240 ? '${text.substring(0, 240)}...' : text;
      return 'HTTP ${response.statusCode}: $snippet';
    }
    return 'HTTP ${response.statusCode}: Server error.';
  }

  Future<void> _bootstrap() async {
    if (!mounted) {
      return;
    }
    final transporter = context.read<TransporterProvider>();
    await transporter.loadDashboardData(prefetchHeavyData: false);
    if (!mounted) {
      return;
    }
    await context.read<AuthProvider>().loadTransporterProfile();
    if (!mounted) {
      return;
    }
    await Future.wait([
      _loadRecipients(),
      _loadBankDetails(),
      _loadBills(),
    ]);
  }

  Future<void> _loadRecipients() async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      return;
    }

    setState(() {
      _loading = true;
    });

    try {
      final response = await http
          .get(
            _buildApiUri('/reports/vehicle-bill/recipients'),
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer ${session.accessToken}',
            },
          )
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception(_errorFromResponse(response));
      }

      final decoded = jsonDecode(response.body);
      final list = decoded is List ? decoded : const [];
      final recipients = <_BillRecipient>[];
      for (final raw in list) {
        if (raw is! Map<String, dynamic>) {
          continue;
        }
        recipients.add(
          _BillRecipient(
            id: raw['id'] as int? ?? 0,
            name: (raw['name'] ?? '').toString(),
            address: (raw['address'] ?? '').toString(),
          ),
        );
      }

      setState(() {
        _recipients = recipients;
        if (_selectedRecipientId == null && recipients.isNotEmpty) {
          _selectedRecipientId = recipients.first.id;
        }
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to load recipients. $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _loadBankDetails() async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      return;
    }

    try {
      final response = await http
          .get(
            _buildApiUri('/reports/vehicle-bill/bank-details'),
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer ${session.accessToken}',
            },
          )
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception(_errorFromResponse(response));
      }

      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) {
        return;
      }
      _bankNameController.text = (decoded['bank_name'] ?? '').toString();
      _bankBranchController.text = (decoded['branch'] ?? '').toString();
      _bankAccountController.text = (decoded['account_no'] ?? '').toString();
      _bankIfscController.text = (decoded['ifsc_code'] ?? '').toString();
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to load bank details. $error')),
      );
    }
  }

  Future<void> _saveBankDetails() async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Session expired. Please login again.')),
      );
      return;
    }

    setState(() {
      _loading = true;
    });

    try {
      final response = await http
          .post(
            _buildApiUri('/reports/vehicle-bill/bank-details'),
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ${session.accessToken}',
            },
            body: jsonEncode(
              {
                'bank_name': _bankNameController.text.trim(),
                'branch': _bankBranchController.text.trim(),
                'account_no': _bankAccountController.text.trim(),
                'ifsc_code': _bankIfscController.text.trim(),
              },
            ),
          )
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception(_errorFromResponse(response));
      }

      await _loadBankDetails();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Bank details saved.')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to save bank details. $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _loadBills() async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      return;
    }

    try {
      final response = await http
          .get(
            _buildApiUri('/reports/vehicle-bill/bills'),
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer ${session.accessToken}',
            },
          )
          .timeout(const Duration(seconds: 25));

      if (response.statusCode != 200) {
        throw Exception(_errorFromResponse(response));
      }

      final decoded = jsonDecode(response.body);
      final list = decoded is List ? decoded : const [];
      final bills = <_SavedBill>[];
      for (final raw in list) {
        if (raw is! Map<String, dynamic>) {
          continue;
        }
        DateTime? billDate;
        DateTime? createdAt;
        final billDateRaw = raw['bill_date']?.toString() ?? '';
        final createdRaw = raw['created_at']?.toString() ?? '';
        if (billDateRaw.isNotEmpty) {
          billDate = DateTime.tryParse(billDateRaw);
        }
        if (createdRaw.isNotEmpty) {
          createdAt = DateTime.tryParse(createdRaw);
        }
        bills.add(
          _SavedBill(
            id: raw['id'] as int? ?? 0,
            billNo: (raw['bill_no'] ?? '').toString(),
            vehicleNumber: (raw['vehicle_number'] ?? '').toString(),
            serviceName: (raw['service_name'] ?? '').toString(),
            totalAmount: (raw['total_amount'] ?? '').toString(),
            month: raw['month'] as int?,
            year: raw['year'] as int?,
            billDate: billDate,
            createdAt: createdAt,
          ),
        );
      }

      if (!mounted) {
        return;
      }
      setState(() {
        _bills = bills;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to load saved bills. $error')),
      );
    }
  }

  Map<String, dynamic>? _buildBillPayloadOrNull() {
    if (!_formKey.currentState!.validate()) {
      return null;
    }

    final provider = context.read<TransporterProvider>();
    if (_selectedVehicleId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select a vehicle.')),
      );
      return null;
    }
    final vehicle = provider.vehicles
        .where((item) => item.id == _selectedVehicleId)
        .toList();
    if (vehicle.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Selected vehicle not found.')),
      );
      return null;
    }

    final month = int.tryParse(_monthController.text.trim());
    final year = int.tryParse(_yearController.text.trim());
    if (month == null || year == null || month < 1 || month > 12) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid month and year.')),
      );
      return null;
    }

    final service = provider.services
        .where((item) => item.id == _selectedServiceId)
        .toList();
    final serviceName = _serviceOverrideController.text.trim().isNotEmpty
        ? _serviceOverrideController.text.trim()
        : (service.isNotEmpty
            ? service.first.name
            : 'Diesel filling Vehicle Rent');

    final baseAmount = _parseAmount(_baseAmountController);
    final extraKm = _parseInt(_extraKmController);
    final extraRate = _parseAmount(_extraRateController);

    final profile = context.read<AuthProvider>().transporterProfile;
    final headerDetails = profile == null
        ? null
        : {
            'company_name': profile.companyName,
            'contact_name': profile.user.username,
            'phone': profile.user.phone,
            'email': profile.user.email,
            'gstin': profile.gstin,
            'pan': profile.pan,
            'website': profile.website,
            'biller_name': profile.user.username,
          };

    return {
      'recipient_id': _selectedRecipientId,
      'vehicle_number': vehicle.first.vehicleNumber,
      'service_name': serviceName,
      'month': month,
      'year': year,
      'bill_date': _billDate.toIso8601String().split('T').first,
      'base_amount': baseAmount.toStringAsFixed(2),
      'extra_km': extraKm,
      'extra_rate': extraRate.toStringAsFixed(2),
      'bank_details': {
        'bank_name': _bankNameController.text.trim(),
        'branch': _bankBranchController.text.trim(),
        'account_no': _bankAccountController.text.trim(),
        'ifsc_code': _bankIfscController.text.trim(),
      },
      if (headerDetails != null) 'header_details': headerDetails,
    };
  }

  Future<File> _writePdfToTemp(List<int> bytes, {String filename = 'bill.pdf'}) async {
    final dir = await getTemporaryDirectory();
    final safeName = filename.replaceAll(RegExp(r'[^A-Za-z0-9_.-]'), '_');
    final file = File('${dir.path}/$safeName');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<File> _writePdfToDocuments(List<int> bytes, String filename) async {
    final dir = await getApplicationDocumentsDirectory();
    final billsDir = Directory('${dir.path}/vehicle_bills');
    if (!await billsDir.exists()) {
      await billsDir.create(recursive: true);
    }
    final safeName = filename.replaceAll(RegExp(r'[^A-Za-z0-9_.-]'), '_');
    final file = File('${billsDir.path}/$safeName');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _previewPdfAndPromptSave() async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Session expired. Please login again.')),
      );
      return;
    }

    final payload = _buildBillPayloadOrNull();
    if (payload == null) {
      return;
    }

    setState(() {
      _loading = true;
    });

    try {
      final response = await http
          .post(
            _buildApiUri('/reports/vehicle-bill/pdf'),
            headers: {
              'Accept': '*/*',
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ${session.accessToken}',
            },
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 40));

      if (!_looksLikePdf(response)) {
        throw Exception(_errorFromResponse(response));
      }

      final billNoHeader = (response.headers['x-bill-no'] ?? '').trim();
      if (billNoHeader.isNotEmpty) {
        payload['bill_no'] = billNoHeader;
      }

      final vehicleNumber = (payload['vehicle_number'] ?? '').toString();
      final month = (payload['month'] ?? '').toString();
      final year = (payload['year'] ?? '').toString();
      final fileLabel = billNoHeader.isNotEmpty ? billNoHeader : '${vehicleNumber}_$month$year';
      final file = await _writePdfToTemp(
        response.bodyBytes,
        filename: 'vehicle_bill_preview_$fileLabel.pdf',
      );

      if (!mounted) {
        return;
      }

      final shouldSave = await showDialog<bool>(
        context: context,
        builder: (dialogContext) {
          return AlertDialog(
            title: const Text('PDF Ready'),
            content: Text(
              billNoHeader.isNotEmpty
                  ? 'Bill No: $billNoHeader\n\nOpen the preview to verify the bill. Save only after confirming.'
                  : 'Open the preview to verify the bill. Save only after confirming.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: const Text('Close'),
              ),
              OutlinedButton.icon(
                onPressed: () async {
                  await OpenFile.open(file.path);
                },
                icon: const Icon(Icons.visibility_outlined),
                label: const Text('Open Preview'),
              ),
              FilledButton.icon(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                icon: const Icon(Icons.cloud_upload_outlined),
                label: const Text('Save'),
              ),
            ],
          );
        },
      );

      if (shouldSave == true) {
        await _saveBillToServer(payload);
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to generate preview PDF. $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _saveBillToServer(Map<String, dynamic> payload) async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      return;
    }

    setState(() {
      _loading = true;
    });

    try {
      final response = await http
          .post(
            _buildApiUri('/reports/vehicle-bill/bills'),
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ${session.accessToken}',
            },
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 45));

      if (response.statusCode != 201 && response.statusCode != 200) {
        throw Exception(_errorFromResponse(response));
      }

      final decoded = jsonDecode(response.body);
      final billNo = decoded is Map<String, dynamic>
          ? (decoded['bill_no'] ?? '').toString()
          : '';

      await _loadBills();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Bill saved. $billNo')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to save bill. $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<List<int>> _fetchBillPdfBytes(int billId) async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      throw Exception('Session expired.');
    }
    final response = await http
        .get(
          _buildApiUri('/reports/vehicle-bill/bills/$billId/download'),
          headers: {
            'Accept': '*/*',
            'Authorization': 'Bearer ${session.accessToken}',
          },
        )
        .timeout(const Duration(seconds: 45));

    if (!_looksLikePdf(response)) {
      throw Exception(_errorFromResponse(response));
    }
    return response.bodyBytes;
  }

  Future<void> _downloadBillPdf(_SavedBill bill) async {
    setState(() {
      _loading = true;
    });

    try {
      final bytes = await _fetchBillPdfBytes(bill.id);
      final filename = bill.billNo.isNotEmpty ? '${bill.billNo}.pdf' : 'vehicle_bill_${bill.id}.pdf';
      final file = await _writePdfToDocuments(bytes, filename);
      await OpenFile.open(file.path);
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Saved: ${file.path}')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to download bill. $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _shareBillPdf(_SavedBill bill) async {
    setState(() {
      _loading = true;
    });

    try {
      final bytes = await _fetchBillPdfBytes(bill.id);
      final filename = bill.billNo.isNotEmpty ? '${bill.billNo}.pdf' : 'vehicle_bill_${bill.id}.pdf';
      final file = await _writePdfToTemp(bytes, filename: filename);
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        text: 'Vehicle Bill ${bill.billNo} ${bill.vehicleNumber} ${bill.periodLabel}',
        subject: filename,
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to share bill. $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _deleteBill(_SavedBill bill) async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Delete Bill?'),
          content: Text(
            bill.billNo.isNotEmpty
                ? 'Delete ${bill.billNo}? This cannot be undone.'
                : 'Delete this bill? This cannot be undone.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) {
      return;
    }

    setState(() {
      _loading = true;
    });

    try {
      final response = await http
          .delete(
            _buildApiUri('/reports/vehicle-bill/bills/${bill.id}'),
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer ${session.accessToken}',
            },
          )
          .timeout(const Duration(seconds: 30));

      if (response.statusCode != 204) {
        throw Exception(_errorFromResponse(response));
      }

      await _loadBills();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Bill deleted.')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to delete bill. $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _openAddRecipientSheet() async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Session expired. Please login again.')),
      );
      return;
    }

    final formKey = GlobalKey<FormState>();
    final nameController = TextEditingController();
    final addressController = TextEditingController();

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
                    'Add Bill Recipient',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: nameController,
                    decoration: const InputDecoration(
                      labelText: 'Name',
                      prefixIcon: Icon(Icons.business_outlined),
                    ),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Name is required';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: addressController,
                    decoration: const InputDecoration(
                      labelText: 'Address (multi-line)',
                      prefixIcon: Icon(Icons.location_on_outlined),
                    ),
                    maxLines: 4,
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Address is required';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 14),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: _loading
                          ? null
                          : () async {
                              if (!formKey.currentState!.validate()) {
                                return;
                              }

                              Navigator.of(sheetContext).pop();
                              setState(() {
                                _loading = true;
                              });

                              try {
                                final response = await http
                                    .post(
                                      _buildApiUri(
                                        '/reports/vehicle-bill/recipients',
                                      ),
                                      headers: {
                                        'Accept': 'application/json',
                                        'Content-Type': 'application/json',
                                        'Authorization':
                                            'Bearer ${session.accessToken}',
                                      },
                                      body: jsonEncode(
                                        {
                                          'name': nameController.text.trim(),
                                          'address':
                                              addressController.text.trim(),
                                        },
                                      ),
                                    )
                                    .timeout(const Duration(seconds: 20));

                                if (response.statusCode != 201) {
                                  throw Exception(_errorFromResponse(response));
                                }
                                final decoded = jsonDecode(response.body);
                                if (decoded is Map<String, dynamic>) {
                                  final recipient = _BillRecipient(
                                    id: decoded['id'] as int? ?? 0,
                                    name: (decoded['name'] ?? '').toString(),
                                    address:
                                        (decoded['address'] ?? '').toString(),
                                  );
                                  setState(() {
                                    _recipients = [..._recipients, recipient];
                                    _selectedRecipientId = recipient.id;
                                  });
                                }
                              } catch (error) {
                                if (!mounted) {
                                  return;
                                }
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: Text(
                                      'Failed to save recipient. $error',
                                    ),
                                  ),
                                );
                              } finally {
                                if (mounted) {
                                  setState(() {
                                    _loading = false;
                                  });
                                }
                              }
                            },
                      icon: const Icon(Icons.save_outlined),
                      label: const Text('Save Recipient'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _pickBillDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _billDate,
      firstDate: DateTime(_billDate.year - 1),
      lastDate: DateTime(_billDate.year + 1),
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _billDate = picked;
    });
  }

  double _parseAmount(TextEditingController controller) {
    final raw = controller.text.trim().replaceAll(',', '');
    return double.tryParse(raw) ?? 0;
  }

  int _parseInt(TextEditingController controller) {
    final raw = controller.text.trim();
    return int.tryParse(raw) ?? 0;
  }

  double get _computedTotal {
    final base = _parseAmount(_baseAmountController);
    final extraKm = _parseInt(_extraKmController).toDouble();
    final rate = _parseAmount(_extraRateController);
    return base + extraKm * rate;
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

  @override
  Widget build(BuildContext context) {
    final transporter = context.watch<TransporterProvider>();
    final vehicles = transporter.vehicles.toList()
      ..sort((a, b) => a.vehicleNumber.compareTo(b.vehicleNumber));
    final services = transporter.services.toList()
      ..sort((a, b) => a.name.compareTo(b.name));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Vehicle Bill PDF'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _bootstrap,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 18),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _SectionCard(
                title: 'Recipient (To)',
                child: Column(
                  children: [
                    DropdownButtonFormField<int?>(
                      initialValue: _selectedRecipientId,
                      decoration: const InputDecoration(
                        labelText: 'Saved recipients',
                        prefixIcon: Icon(Icons.business),
                      ),
                      items: [
                        for (final rec in _recipients)
                          DropdownMenuItem<int?>(
                            value: rec.id,
                            child: Text(rec.label),
                          ),
                      ],
                      onChanged: _loading
                          ? null
                          : (value) {
                              setState(() {
                                _selectedRecipientId = value;
                              });
                            },
                      validator: (value) {
                        if (_recipients.isEmpty) {
                          return 'Add a recipient first';
                        }
                        if (value == null) {
                          return 'Select a recipient';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: _loading ? null : _openAddRecipientSheet,
                        icon: const Icon(Icons.add_location_alt_outlined),
                        label: const Text('Add Recipient'),
                      ),
                    ),
                  ],
                ),
              ),
              _SectionCard(
                title: 'Bill Period',
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: _monthController,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Month',
                              prefixIcon: Icon(Icons.calendar_month_outlined),
                            ),
                            validator: (value) {
                              final month = int.tryParse(value?.trim() ?? '');
                              if (month == null || month < 1 || month > 12) {
                                return '1-12';
                              }
                              return null;
                            },
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextFormField(
                            controller: _yearController,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Year',
                              prefixIcon: Icon(Icons.event_outlined),
                            ),
                            validator: (value) {
                              final year = int.tryParse(value?.trim() ?? '');
                              if (year == null || year < 2000 || year > 2100) {
                                return 'Invalid';
                              }
                              return null;
                            },
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: _loading ? null : _pickBillDate,
                        icon: const Icon(Icons.edit_calendar_outlined),
                        label: Text(
                          'Bill Date: ${_billDate.day.toString().padLeft(2, '0')}/${_billDate.month.toString().padLeft(2, '0')}/${_billDate.year}',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              _SectionCard(
                title: 'Vehicle & Service',
                child: Column(
                  children: [
                    DropdownButtonFormField<int?>(
                      initialValue: _selectedVehicleId,
                      decoration: const InputDecoration(
                        labelText: 'Vehicle number',
                        prefixIcon: Icon(Icons.local_shipping_outlined),
                      ),
                      items: [
                        for (final vehicle in vehicles)
                          DropdownMenuItem<int?>(
                            value: vehicle.id,
                            child: Text(vehicle.vehicleNumber),
                          ),
                      ],
                      onChanged: _loading
                          ? null
                          : (value) {
                              setState(() {
                                _selectedVehicleId = value;
                              });
                            },
                      validator: (value) =>
                          value == null ? 'Select a vehicle' : null,
                    ),
                    const SizedBox(height: 10),
                    DropdownButtonFormField<int?>(
                      initialValue: _selectedServiceId,
                      decoration: const InputDecoration(
                        labelText: 'Service (optional)',
                        prefixIcon: Icon(Icons.miscellaneous_services_outlined),
                      ),
                      items: [
                        const DropdownMenuItem<int?>(
                          value: null,
                          child: Text('Custom / Not selected'),
                        ),
                        for (final service in services)
                          DropdownMenuItem<int?>(
                            value: service.id,
                            child: Text(service.name),
                          ),
                      ],
                      onChanged: _loading
                          ? null
                          : (value) {
                              setState(() {
                                _selectedServiceId = value;
                              });
                            },
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _serviceOverrideController,
                      decoration: const InputDecoration(
                        labelText: 'Service name (optional override)',
                        prefixIcon: Icon(Icons.edit_outlined),
                      ),
                    ),
                  ],
                ),
              ),
              _SectionCard(
                title: 'Charges',
                child: Column(
                  children: [
                    TextFormField(
                      controller: _baseAmountController,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'Monthly rent amount',
                        prefixIcon: Icon(Icons.currency_rupee_outlined),
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: _extraKmController,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Extra KM',
                              prefixIcon: Icon(Icons.add_road_outlined),
                            ),
                            onChanged: (_) => setState(() {}),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextFormField(
                            controller: _extraRateController,
                            keyboardType: const TextInputType.numberWithOptions(
                              decimal: true,
                            ),
                            decoration: const InputDecoration(
                              labelText: 'Rate / KM',
                              prefixIcon: Icon(Icons.price_change_outlined),
                            ),
                            onChanged: (_) => setState(() {}),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'Total: ₹${_computedTotal.toStringAsFixed(2)}',
                        style: const TextStyle(
                          fontWeight: FontWeight.w800,
                          fontSize: 16,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              _SectionCard(
                title: 'Bank Details',
                child: Column(
                  children: [
                    TextFormField(
                      controller: _bankNameController,
                      decoration: const InputDecoration(
                        labelText: 'Bank',
                        prefixIcon: Icon(Icons.account_balance_outlined),
                      ),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _bankBranchController,
                      decoration: const InputDecoration(
                        labelText: 'Branch',
                        prefixIcon: Icon(Icons.account_tree_outlined),
                      ),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _bankAccountController,
                      decoration: const InputDecoration(
                        labelText: 'Account No.',
                        prefixIcon: Icon(Icons.numbers_outlined),
                      ),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _bankIfscController,
                      decoration: const InputDecoration(
                        labelText: 'IFSC Code',
                        prefixIcon: Icon(Icons.verified_outlined),
                      ),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: _loading ? null : _saveBankDetails,
                        icon: const Icon(Icons.save_outlined),
                        label: const Text('Save Bank Details'),
                      ),
                    ),
                  ],
                ),
              ),
              _SectionCard(
                title: 'Header (From)',
                child: Consumer<AuthProvider>(
                  builder: (context, auth, _) {
                    final profile = auth.transporterProfile;
                    if (profile == null) {
                      return const Text(
                        'Header details are taken from your Profile. Pull to refresh, or update your profile first.',
                      );
                    }

                    return Column(
                      children: [
                        _InfoRow(
                          label: 'Company',
                          value: profile.companyName,
                        ),
                        _InfoRow(
                          label: 'Email',
                          value: profile.user.email,
                        ),
                        _InfoRow(
                          label: 'Phone',
                          value: profile.user.phone,
                        ),
                        _InfoRow(
                          label: 'GSTIN',
                          value: profile.gstin,
                        ),
                        _InfoRow(
                          label: 'PAN',
                          value: profile.pan,
                        ),
                        _InfoRow(
                          label: 'Website',
                          value: profile.website,
                        ),
                        _InfoRow(
                          label: 'Address',
                          value: profile.address,
                          isLast: true,
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: () async {
                              await Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => const TransporterProfileScreen(),
                                ),
                              );
                              if (!context.mounted) {
                                return;
                              }
                              await context
                                  .read<AuthProvider>()
                                  .loadTransporterProfile();
                            },
                            icon: const Icon(Icons.edit_outlined),
                            label: const Text('Edit in Profile'),
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
              const SizedBox(height: 4),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _loading ? null : _previewPdfAndPromptSave,
                  icon: const Icon(Icons.visibility_outlined),
                  label: const Text('Preview PDF'),
                ),
              ),
              const SizedBox(height: 12),
              _SectionCard(
                title: 'Saved Bills',
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            _bills.isEmpty
                                ? 'No bills saved yet.'
                                : 'Latest bills: ${_bills.length}',
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                        ),
                        IconButton(
                          onPressed: _loading ? null : _loadBills,
                          icon: const Icon(Icons.refresh),
                          tooltip: 'Refresh bills',
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    if (_bills.isNotEmpty)
                      ListView.separated(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: _bills.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, index) {
                          final bill = _bills[index];
                          final title = bill.billNo.isNotEmpty
                              ? bill.billNo
                              : 'Bill #${bill.id}';
                          final subtitleParts = <String>[];
                          if (bill.vehicleNumber.trim().isNotEmpty) {
                            subtitleParts.add(bill.vehicleNumber.trim());
                          }
                          if (bill.periodLabel.isNotEmpty) {
                            subtitleParts.add(bill.periodLabel);
                          }
                          if (bill.serviceName.trim().isNotEmpty) {
                            subtitleParts.add(bill.serviceName.trim());
                          }
                          if (bill.totalAmount.trim().isNotEmpty) {
                            subtitleParts.add('₹${bill.totalAmount}');
                          }
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text(
                              title,
                              style: const TextStyle(fontWeight: FontWeight.w700),
                            ),
                            subtitle: Text(subtitleParts.join(' • ')),
                            trailing: PopupMenuButton<String>(
                              onSelected: (value) async {
                                if (value == 'download') {
                                  await _downloadBillPdf(bill);
                                } else if (value == 'share') {
                                  await _shareBillPdf(bill);
                                } else if (value == 'delete') {
                                  await _deleteBill(bill);
                                }
                              },
                              itemBuilder: (_) => const [
                                PopupMenuItem(
                                  value: 'download',
                                  child: Text('Download'),
                                ),
                                PopupMenuItem(
                                  value: 'share',
                                  child: Text('Share'),
                                ),
                                PopupMenuItem(
                                  value: 'delete',
                                  child: Text('Delete'),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              if (_loading)
                const Center(
                  child: Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: CircularProgressIndicator(),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0.6,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.label,
    required this.value,
    this.isLast = false,
  });

  final String label;
  final String value;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final normalized = value.trim();
    final display = normalized.isEmpty ? 'Not set' : normalized;

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: isLast
            ? null
            : Border(
                bottom: BorderSide(
                  color: colors.outline.withValues(alpha: 0.16),
                ),
              ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: colors.onSurface.withValues(alpha: 0.65),
                    fontWeight: FontWeight.w600,
                  ),
            ),
          ),
          Expanded(
            child: Text(
              display,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
