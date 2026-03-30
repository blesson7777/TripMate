# TripMate

TripMate is a transport operations platform with one Django backend, one admin web console, and two separate Flutter Android applications:

- `TripMate Driver`
- `TripMate Transporter`

The system manages daily runs, attendance, vehicle and service allocation, odometer capture, vehicle fuel fills, tower diesel fills, salary processing, PDF reporting, push notifications, and APK self-updates.

## Architecture

### Backend
- Django 6
- Django REST Framework
- SimpleJWT
- PostgreSQL
- ReportLab for PDF generation
- Firebase Cloud Messaging integration

### Mobile
- Flutter
- Android product flavors:
  - `driver`
  - `transporter`

### Admin Web
- Django-rendered admin console for operations, audits, manual corrections, releases, and reporting

## Core Modules

### Authentication and Accounts
- Separate transporter and driver registration flows
- Email OTP verification
- Login with phone or email plus password
- Forgot password with email OTP
- Force password reset from admin

### Attendance and Run Sessions
- Driver `Start Day` opens a run session
- Driver `End Day` closes the active run session
- Attendance is auto-marked `PRESENT` on successful start
- Transporter can mark `PRESENT`, `ABSENT`, or `LEAVE`
- Admin can force-close sessions or force absence when operational corrections are required
- Attendance and salary calculations use the driver join date for the current transporter

### Vehicle and Service Logic
- One open session per driver
- One open session per vehicle
- Service selection per run
- Vehicle selection per run
- Odometer continuity validation against the latest known reading
- Optional destination and service purpose capture

### Vehicle Fuel Module
- Vehicle fuel entry with:
  - liters
  - amount
  - odometer reading
  - odometer photo
  - bill/slip photo
- Automatic current vehicle selection when a day is active
- Manual vehicle selection when no active day exists
- Tank balance, average mileage, and estimated remaining fuel analytics

### Tower Diesel Module
- Separate from vehicle fuel refilling
- Logbook photo required
- Manual site entry with tower master lookup
- Tower fill only allowed when the driver is within 100 meters of the saved tower coordinates
- First driver fill can set tower coordinates if the tower has none
- Later driver fills do not overwrite tower coordinates
- Nearby tower map with search, distance sorting, and Google Maps navigation

### Salary Module
- Monthly salary per driver
- Advance payments and settlement
- Sundays as weekly off, with first partial-week Sunday after joining treated as unpaid
- `No Duty` treated as paid according to current business logic
- Salary due date logic
- Monthly salary payment records with paid date/time and payer
- Professional salary balance emails
- Admin/manual salary email send
- Transporter-level auto salary email toggle

### Reports and PDFs
- Monthly trip sheets
- Vehicle-wise and service-wise summaries
- Diesel fill PDF with vehicle-change handling and optional filled-quantity column
- Admin diesel manual entry and vehicle trip manual correction flows

### Notifications
- Driver and transporter push notifications
- In-app notification feeds with mark-read and mark-all-read support
- Scheduled reminders
- App update notifications
- Admin broadcast notifications

### App Update System
- Public update endpoints for driver and transporter apps
- APK download and Android installer handoff
- Background update download via Android `DownloadManager`
- Admin release publishing from the web console

## Repository Layout

```text
attendance/   Attendance, marks, services
 diesel/       Tower diesel site and PDF logic
 drivers/      Driver profiles and transporter allocation
 fuel/         Vehicle fuel records and analytics
 mobile_app/   Flutter driver and transporter apps
 reports/      Aggregated reporting APIs
 salary/       Salary calculations, advances, payments, email
 templates/    Admin web templates
 trips/        Run session and trip APIs
 users/        Users, OTP, notifications, app releases, FCM
 vehicles/     Vehicle master data
 tripmate/     Django project settings, admin web routes, utilities
```

## Local Setup

### Prerequisites
- Python 3.12+
- PostgreSQL 14+
- Flutter SDK 3.41+
- Android SDK / Android Studio
- Java 17

### 1. Backend setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

### 2. Mobile setup

```bash
cd mobile_app
flutter pub get
```

## Environment Variables

See `.env.example`.

Important keys:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DJANGO_EMAIL_*`
- `FCM_SERVER_KEY`
- `FCM_PROJECT_ID`
- `FCM_SERVICE_ACCOUNT_FILE`
- `FCM_SERVICE_ACCOUNT_JSON`

Do not commit:
- `.env`
- Firebase service account JSON
- production secrets
- local `google-services.json`

## Running the Mobile Apps

From `mobile_app/`:

### Driver

```bash
flutter run --flavor driver -t lib/main_driver.dart --dart-define=API_BASE_URL=https://13-60-219-105.sslip.io/api
```

### Transporter

```bash
flutter run --flavor transporter -t lib/main_transporter.dart --dart-define=API_BASE_URL=https://13-60-219-105.sslip.io/api
```

## Release Builds

From `mobile_app/`:

### Driver APK

```bash
flutter build apk --release --flavor driver -t lib/main_driver.dart --target-platform android-arm64 --build-number 3036 --dart-define=API_BASE_URL=https://13-60-219-105.sslip.io/api
```

### Transporter APK

```bash
flutter build apk --release --flavor transporter -t lib/main_transporter.dart --target-platform android-arm64 --build-number 3036 --dart-define=API_BASE_URL=https://13-60-219-105.sslip.io/api
```

### Install with ADB

```bash
adb devices
adb install -r .\build\app\outputs\flutter-apk\app-driver-release.apk
adb install -r .\build\app\outputs\flutter-apk\app-transporter-release.apk
```

## Publishing App Updates

The backend exposes:

- `/api/app-update/driver`
- `/api/app-update/transporter`

Admin release page:

- `/admin/app-releases/`

Release flow:

1. Build the APK with a higher build number.
2. Open admin app releases.
3. Upload the APK for the correct variant.
4. Publish the release.
5. The server marks it active and pushes update notifications.

## Admin Web Console

Main admin routes:

- `/admin/transporters/`
- `/admin/drivers/`
- `/admin/vehicles/`
- `/admin/attendance/`
- `/admin/trips/`
- `/admin/fuel-records/`
- `/admin/diesel-sites/`
- `/admin/diesel-manual-entry/`
- `/admin/manual-vehicle-trips/`
- `/admin/reports/monthly/`
- `/admin/notifications/`
- `/admin/app-releases/`

Admin capabilities include:
- transporter management
- driver allocation and removal
- diesel module enable/disable
- attendance overrides
- session force-close and KM correction
- manual diesel and vehicle trip entry
- app release publishing
- admin push/broadcast messaging
- salary auto-mail toggle and manual salary email send

## AWS Deployment

This project is already structured for Ubuntu + systemd + nginx.

Files provided:
- `tripmate.service`
- `nginx_tripmate.conf`
- `deploy/aws/ec2/bootstrap_ubuntu.sh`
- `deploy/aws/ec2/deploy_remote.sh`
- `deploy/aws/ec2/deploy_from_windows.ps1`
- `deploy/aws/ec2/.env.production.example`

Typical deploy flow:

```bash
chmod +x deploy/aws/ec2/bootstrap_ubuntu.sh deploy/aws/ec2/deploy_remote.sh
sudo APP_USER=ubuntu APP_DIR=/home/ubuntu/tripmate-backend bash deploy/aws/ec2/bootstrap_ubuntu.sh
cp deploy/aws/ec2/.env.production.example .env
# edit .env with production values
```

The production host currently used in the project is:

- `https://13-60-219-105.sslip.io`

From Windows, upload and deploy the backend bundle to EC2 with:

```powershell
.\deploy\aws\ec2\deploy_from_windows.ps1 `
  -RemoteHost 13.60.219.105 `
  -KeyPath C:\path\to\tripmate.pem `
  -ServerName 13-60-219-105.sslip.io `
  -TlsDomain 13-60-219-105.sslip.io `
  -LetsEncryptEmail you@example.com
```

If this is the first deployment on a fresh Ubuntu instance, add `-Bootstrap`.

## Test Commands

### Backend

```bash
python manage.py check
python manage.py test
```

### Flutter

```bash
cd mobile_app
flutter analyze
```

## Operational Notes

- Driver and transporter apps are different Android packages and can be installed on the same phone.
- APK installation from inside the app opens the Android package installer; silent installation is not possible on normal Android devices.
- APK update delivery speed depends mainly on APK size, network conditions, and server hosting. The repository is currently configured for direct nginx media serving.
- Release shrinking is enabled for Android release builds to reduce APK size.

## Status

This repository contains both source code and production-focused operational tooling for the TripMate deployment currently running on AWS.
