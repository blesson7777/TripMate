import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class DriverAllocationScreen extends StatefulWidget {
  const DriverAllocationScreen({super.key});

  @override
  State<DriverAllocationScreen> createState() => _DriverAllocationScreenState();
}

class _DriverAllocationScreenState extends State<DriverAllocationScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _otpController = TextEditingController();

  @override
  void dispose() {
    _emailController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _sendOtp() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Driver email is required')),
      );
      return;
    }

    final valid = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email);
    if (!valid) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid driver email')),
      );
      return;
    }

    final sent = await context
        .read<TransporterProvider>()
        .requestDriverAllocationOtp(email: email);
    if (!mounted) {
      return;
    }
    if (!sent) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.read<TransporterProvider>().error ?? 'Unable to send OTP',
          ),
        ),
      );
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('OTP sent to driver email')),
    );
  }

  Future<void> _verifyAndAllocate() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    final success = await context.read<TransporterProvider>().verifyDriverAllocationOtp(
          email: _emailController.text.trim(),
          otp: _otpController.text.trim(),
        );
    if (!mounted) {
      return;
    }

    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.read<TransporterProvider>().error ?? 'Unable to verify OTP',
          ),
        ),
      );
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Driver allocated successfully')),
    );
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFFE7F1F0),
              Color(0xFFF8F1E6),
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: StaggeredEntrance(
                delay: const Duration(milliseconds: 120),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.94),
                      borderRadius: BorderRadius.circular(30),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.08),
                          blurRadius: 26,
                          offset: const Offset(0, 16),
                        ),
                      ],
                    ),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(22, 20, 22, 22),
                      child: Consumer<TransporterProvider>(
                        builder: (context, provider, _) {
                          return Form(
                            key: _formKey,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Text(
                                      'Allocate Driver',
                                      style: Theme.of(context).textTheme.titleLarge,
                                    ),
                                    const Spacer(),
                                    IconButton(
                                      onPressed: () => Navigator.pop(context),
                                      icon: const Icon(Icons.close_rounded),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Enter the registered driver email, send OTP, and verify.',
                                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                        color: Colors.black.withValues(alpha: 0.7),
                                      ),
                                ),
                                const SizedBox(height: 16),
                                TextFormField(
                                  controller: _emailController,
                                  keyboardType: TextInputType.emailAddress,
                                  decoration: const InputDecoration(
                                    labelText: 'Driver Email',
                                    prefixIcon: Icon(Icons.mail_outline),
                                  ),
                                  validator: (value) {
                                    final text = value?.trim() ?? '';
                                    if (text.isEmpty) {
                                      return 'Email is required';
                                    }
                                    final valid =
                                        RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
                                            .hasMatch(text);
                                    if (!valid) {
                                      return 'Enter valid email';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 10),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: FilledButton.tonalIcon(
                                    onPressed: provider.loading ? null : _sendOtp,
                                    icon: const Icon(Icons.mark_email_read_outlined),
                                    label: const Text('Send OTP'),
                                  ),
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: _otpController,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(
                                    labelText: 'OTP',
                                    prefixIcon: Icon(Icons.verified_user_outlined),
                                  ),
                                  validator: (value) {
                                    final text = value?.trim() ?? '';
                                    if (text.isEmpty) {
                                      return 'OTP is required';
                                    }
                                    if (text.length != 6) {
                                      return 'OTP must be 6 digits';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 16),
                                FilledButton.icon(
                                  onPressed: provider.loading ? null : _verifyAndAllocate,
                                  icon: provider.loading
                                      ? const SizedBox(
                                          width: 16,
                                          height: 16,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white,
                                          ),
                                        )
                                      : const Icon(Icons.verified_rounded),
                                  label: const Text('Verify & Allocate'),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
