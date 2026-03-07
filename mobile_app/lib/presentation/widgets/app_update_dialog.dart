import 'package:flutter/material.dart';

import '../../core/models/app_update_info.dart';
import '../../core/services/app_update_service.dart';

class AppUpdateDialog extends StatefulWidget {
  const AppUpdateDialog({
    super.key,
    required this.updateInfo,
    required this.updateService,
  });

  final AppUpdateInfo updateInfo;
  final AppUpdateService updateService;

  @override
  State<AppUpdateDialog> createState() => _AppUpdateDialogState();
}

class _AppUpdateDialogState extends State<AppUpdateDialog> {
  bool _isDownloading = false;
  bool _isInstalling = false;
  bool _backgroundQueued = false;
  double _progress = 0;
  String? _errorMessage;

  Future<void> _startUpdate() async {
    setState(() {
      _isDownloading = true;
      _isInstalling = false;
      _progress = 0;
      _errorMessage = null;
    });

    try {
      final apkPath = await widget.updateService.downloadUpdate(
        updateInfo: widget.updateInfo,
        onProgress: (progress) {
          if (!mounted) {
            return;
          }
          setState(() {
            _progress = progress;
          });
        },
      );

      if (!mounted) {
        return;
      }

      if (widget.updateService.isBackgroundManagedDownload(apkPath)) {
        setState(() {
          _isDownloading = false;
          _isInstalling = false;
          _backgroundQueued = true;
          _errorMessage = null;
        });
        return;
      }

      setState(() {
        _isDownloading = false;
        _isInstalling = true;
      });

      final launched = await widget.updateService.installUpdate(apkPath);
      if (!mounted) {
        return;
      }

      if (!launched) {
        setState(() {
          _isInstalling = false;
          _errorMessage =
              'Unable to open the installer. Allow app installs for TripMate and try again.';
        });
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isDownloading = false;
        _isInstalling = false;
        _errorMessage = 'Download failed. Check your connection and retry.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final message = widget.updateInfo.message.isNotEmpty
        ? widget.updateInfo.message
        : 'A new version of ${widget.updateInfo.channel.displayName} is available.';

    return PopScope(
      canPop: _backgroundQueued ||
          (!widget.updateInfo.forceUpdate &&
              !_isDownloading &&
              !_isInstalling),
      child: AlertDialog(
        title: const Text('Update Available'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(message),
            const SizedBox(height: 12),
            Text(
              'Latest version ${widget.updateInfo.latestVersion} '
              '(build ${widget.updateInfo.latestBuildNumber})',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (_backgroundQueued) ...[
              const SizedBox(height: 18),
              Text(
                widget.updateService.backgroundDownloadMessage(widget.updateInfo),
              ),
            ],
            if (_isDownloading || _isInstalling) ...[
              const SizedBox(height: 18),
              LinearProgressIndicator(
                value: _isInstalling ? null : _progress.clamp(0, 1),
              ),
              const SizedBox(height: 10),
              Text(
                _isInstalling
                    ? 'Opening installer...'
                    : 'Downloading update... ${(_progress * 100).toStringAsFixed(0)}% complete',
              ),
            ],
            if (_errorMessage != null) ...[
              const SizedBox(height: 14),
              Text(
                _errorMessage!,
                style: const TextStyle(color: Colors.redAccent),
              ),
            ],
          ],
        ),
        actions: [
          if (_backgroundQueued)
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Done'),
            )
          else if (!widget.updateInfo.forceUpdate)
            TextButton(
              onPressed: (_isDownloading || _isInstalling)
                  ? null
                  : () => Navigator.of(context).pop(),
              child: const Text('Later'),
            ),
          if (!_backgroundQueued)
            TextButton(
              onPressed:
                  (_isDownloading || _isInstalling) ? null : _startUpdate,
              child: Text(_errorMessage == null ? 'Update Now' : 'Retry'),
            ),
        ],
      ),
    );
  }
}
