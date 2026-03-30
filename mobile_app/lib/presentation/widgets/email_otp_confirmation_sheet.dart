import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';

Future<String?> showEmailOtpConfirmationSheet({
  required BuildContext context,
  required String emailAddress,
  required String title,
  required String subtitle,
  required String confirmLabel,
}) {
  final otpController = TextEditingController();
  final formKey = GlobalKey<FormState>();
  bool otpSent = false;

  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) {
      return Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
        ),
        child: StatefulBuilder(
          builder: (context, setSheetState) {
            Future<void> sendOtp() async {
              final auth = sheetContext.read<AuthProvider>();
              final sent = await auth.requestAccountDeletionOtp();
              if (!sheetContext.mounted) {
                return;
              }
              if (!sent) {
                ScaffoldMessenger.of(sheetContext).showSnackBar(
                  SnackBar(
                    content: Text(auth.error ?? 'Unable to send OTP'),
                  ),
                );
                return;
              }
              setSheetState(() {
                otpSent = true;
              });
              ScaffoldMessenger.of(sheetContext).showSnackBar(
                SnackBar(content: Text('OTP sent to $emailAddress')),
              );
            }

            return Container(
              decoration: const BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
              ),
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
              child: Form(
                key: formKey,
                child: SingleChildScrollView(
                  child: Consumer<AuthProvider>(
                    builder: (context, auth, _) {
                      final colors = Theme.of(context).colorScheme;
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Center(
                            child: Container(
                              width: 44,
                              height: 4,
                              decoration: BoxDecoration(
                                color: colors.outline.withValues(alpha: 0.35),
                                borderRadius: BorderRadius.circular(999),
                              ),
                            ),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            title,
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(height: 6),
                          Text(
                            subtitle,
                            style:
                                Theme.of(context).textTheme.bodyMedium?.copyWith(
                                      color:
                                          colors.onSurface.withValues(alpha: 0.7),
                                    ),
                          ),
                          const SizedBox(height: 16),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF6F9FA),
                              borderRadius: BorderRadius.circular(18),
                              border: Border.all(
                                color: colors.outline.withValues(alpha: 0.18),
                              ),
                            ),
                            child: Row(
                              children: [
                                Icon(
                                  Icons.mail_outline_rounded,
                                  color: colors.primary,
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    emailAddress,
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodyLarge
                                        ?.copyWith(fontWeight: FontWeight.w700),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 14),
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton.tonalIcon(
                              onPressed: auth.isLoading ? null : sendOtp,
                              icon: const Icon(Icons.send_rounded),
                              label: Text(otpSent ? 'Resend OTP' : 'Send OTP'),
                            ),
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: otpController,
                            keyboardType: TextInputType.number,
                            maxLength: 6,
                            decoration: InputDecoration(
                              labelText: 'Email OTP',
                              counterText: '',
                              prefixIcon:
                                  const Icon(Icons.verified_outlined),
                              helperText: otpSent
                                  ? 'Enter the OTP sent to the registered email.'
                                  : 'Send OTP before continuing.',
                            ),
                            validator: (value) {
                              if ((value ?? '').trim().length != 6) {
                                return 'Enter the 6-digit OTP';
                              }
                              return null;
                            },
                          ),
                          if (kDebugMode && auth.debugOtp != null) ...[
                            const SizedBox(height: 10),
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: colors.primary.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: Text(
                                'Debug OTP: ${auth.debugOtp}',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodyMedium
                                    ?.copyWith(
                                      color: colors.primary,
                                      fontWeight: FontWeight.w700,
                                    ),
                              ),
                            ),
                          ],
                          const SizedBox(height: 16),
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton.icon(
                              onPressed: auth.isLoading
                                  ? null
                                  : () {
                                      if (!formKey.currentState!.validate()) {
                                        return;
                                      }
                                      Navigator.of(sheetContext)
                                          .pop(otpController.text.trim());
                                    },
                              icon: auth.isLoading
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white,
                                      ),
                                    )
                                  : const Icon(Icons.delete_outline_rounded),
                              label: Text(confirmLabel),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ),
            );
          },
        ),
      );
    },
  ).whenComplete(() {
    otpController.dispose();
  });
}
