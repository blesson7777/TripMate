# TripMate Fleet Management System

Full-stack fleet management platform for transport companies.

## Stack

- Backend: Django, Django REST Framework, PostgreSQL, JWT (`simplejwt`)
- Mobile Apps: Flutter (separate Driver app and Transporter app, clean architecture)
- Admin Panel: Django template-based dashboard (TripMate fleet design)
- Media: Django `media/` storage for odometer and fuel images

## Roles

- `ADMIN`
- `TRANSPORTER`
- `DRIVER`

## Core Business Rules

1. Driver must start attendance before adding trip/fuel entries.
2. One driver can have zero or many trips in a day.
3. Trips are linked to attendance.
4. Fuel records are linked to attendance.
5. Odometer photos are stored for verification.
6. GPS latitude/longitude is captured at attendance start.

## 1) Django Project Structure

```text
tripmate/
  manage.py
  requirements.txt
  .env.example
  tripmate/
    settings.py
    urls.py
    admin_dashboard_urls.py
    admin_dashboard_views.py
  users/
    models.py
    serializers.py
    views.py
    permissions.py
    urls.py
  vehicles/
    models.py
    serializers.py
    views.py
    urls.py
  drivers/
    models.py
    serializers.py
    views.py
    urls.py
  attendance/
    models.py
    serializers.py
    views.py
    urls.py
  trips/
    models.py
    serializers.py
    views.py
    urls.py
  fuel/
    models.py
    serializers.py
    views.py
    urls.py
  reports/
    serializers.py
    views.py
    urls.py
  templates/admin/
    layout.html
    dashboard.html
    users.html
    user_details.html
    transporters.html
    vehicles.html
    drivers.html
    attendance.html
    trips.html
    fuel_records.html
    monthly_reports.html
```

## 2) Django Models

Implemented in app models:

- `users.User` (custom user): `username`, `password`, `role`, `phone`
- `users.Transporter`: `user`, `company_name`, `address`
- `vehicles.Vehicle`: `transporter`, `vehicle_number`, `model`, `status`
- `drivers.Driver`: `user`, `transporter`, `license_number`, `assigned_vehicle`
- `attendance.Attendance`: `driver`, `vehicle`, `date`, `status`, `start_km`, `end_km`, `odo_start_image`, `odo_end_image`, `latitude`, `longitude`
- `trips.Trip`: `attendance`, `start_location`, `destination`, `start_km`, `end_km`, `total_km`, `purpose`
- `fuel.FuelRecord`: `attendance`, `driver`, `vehicle`, `liters`, `amount`, `meter_image`, `bill_image`, `date`

## 3) Django Serializers

- Auth/User: `UserSerializer`, `LoginSerializer`
- Attendance: `AttendanceSerializer`, `AttendanceStartSerializer`, `AttendanceEndSerializer`
- Trips: `TripSerializer`, `TripCreateSerializer`
- Fuel: `FuelRecordSerializer`, `FuelRecordCreateSerializer`
- Reports: `MonthlyReportSerializer`, `MonthlyTripSheetRowSerializer`
- List serializers for vehicles and drivers included.

## 4) Django API Views

- JWT login: `LoginView`
- Driver workflow:
  - `AttendanceStartView`
  - `TripCreateView`
  - `FuelAddView`
  - `AttendanceEndView`
- List/report views:
  - `VehicleListView`
  - `DriverListView`
  - `TripListView`
  - `FuelRecordListView`
  - `MonthlyReportView`

## 5) URL Routes

API routes under `/api/`:

- `POST /api/login`
- `POST /api/attendance/start`
- `POST /api/trips/create`
- `POST /api/fuel/add`
- `POST /api/attendance/end`
- `GET /api/vehicles`
- `GET /api/drivers`
- `GET /api/trips`
- `GET /api/fuel`
- `GET /api/reports/monthly`

Admin dashboard routes under `/admin/`:

- Dashboard, Users, Transporters, Vehicles, Drivers, Attendance, Trips, Fuel Records, Monthly Reports, Audit Logs, CSV export pages.

## 6) Flutter Project Structure

```text
mobile_app/
  pubspec.yaml
  lib/
    main.dart
    main_driver.dart
    main_transporter.dart
    core/
      constants/api_constants.dart
      network/api_client.dart
      services/location_service.dart
      services/ocr_service.dart
    domain/
      entities/
      repositories/
    data/
      models/
      datasources/
      repositories/
    presentation/
      providers/
      screens/common/
      screens/driver/
      screens/transporter/
      widgets/
```

## 7) Flutter API Service Layer

- `ApiClient`: JSON + multipart requests, bearer token support, central error handling.
- `AuthRemoteDataSource`: `POST /login`
- `FleetRemoteDataSource`:
  - start/end attendance
  - create trip
  - add fuel
  - get vehicles/drivers/trips/fuel
  - get monthly report
- Repository layer:
  - `AuthRepositoryImpl`
  - `FleetRepositoryImpl`

## 8) Flutter Screens

Driver App:

- Login
- Driver Dashboard
- Start Day (camera + OCR + GPS)
- Add Trip
- Fuel Entry
- End Day
- Trip History

Transporter App:

- Login
- Transporter Dashboard
- Vehicles
- Drivers
- Trips
- Fuel Records
- Reports (Monthly Trip Sheet)

Both apps now run from separate entry points:

- Driver app: `lib/main_driver.dart`
- Transporter app: `lib/main_transporter.dart`

## 9) Sample API Request/Response

### Login

```http
POST /api/login
Content-Type: application/json

{
  "username": "driver1",
  "password": "Password@123"
}
```

```json
{
  "refresh": "<refresh_token>",
  "access": "<access_token>",
  "user": {
    "id": 12,
    "username": "driver1",
    "email": "",
    "phone": "9999999999",
    "role": "DRIVER"
  },
  "driver_id": 5
}
```

### Start Day (Attendance)

```http
POST /api/attendance/start
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

start_km=152340
latitude=22.572645
longitude=88.363892
odo_start_image=<file>
```

```json
{
  "id": 8,
  "driver": 5,
  "driver_name": "driver1",
  "vehicle": 3,
  "vehicle_number": "WB12AB1234",
  "date": "2026-03-04",
  "status": "ON_DUTY",
  "start_km": 152340,
  "end_km": null,
  "latitude": "22.572645",
  "longitude": "88.363892"
}
```

### Add Trip

```http
POST /api/trips/create
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "start_location": "Kolkata Depot",
  "destination": "Howrah Yard",
  "start_km": 152340,
  "end_km": 152372,
  "purpose": "Material delivery"
}
```

```json
{
  "id": 19,
  "attendance": 8,
  "attendance_date": "2026-03-04",
  "driver_name": "driver1",
  "vehicle_number": "WB12AB1234",
  "start_location": "Kolkata Depot",
  "destination": "Howrah Yard",
  "start_km": 152340,
  "end_km": 152372,
  "total_km": 32,
  "purpose": "Material delivery",
  "created_at": "2026-03-04T11:42:00Z"
}
```

### Add Fuel

```http
POST /api/fuel/add
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

liters=20.5
amount=2190
meter_image=<file>
bill_image=<file>
```

```json
{
  "id": 17,
  "attendance": 8,
  "driver": 5,
  "driver_name": "driver1",
  "vehicle": 3,
  "vehicle_number": "WB12AB1234",
  "liters": "20.50",
  "amount": "2190.00",
  "date": "2026-03-04"
}
```

### End Day

```http
POST /api/attendance/end
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

end_km=152410
odo_end_image=<file>
```

```json
{
  "id": 8,
  "driver": 5,
  "vehicle": 3,
  "date": "2026-03-04",
  "status": "ON_DUTY",
  "start_km": 152340,
  "end_km": 152410,
  "trips_count": 1
}
```

### Vehicles List

```http
GET /api/vehicles
Authorization: Bearer <access_token>
```

```json
[
  {
    "id": 3,
    "transporter_id": 2,
    "transporter_company": "Swift Logistics",
    "vehicle_number": "WB12AB1234",
    "model": "Tata 407",
    "status": "ACTIVE"
  }
]
```

### Monthly Report

```http
GET /api/reports/monthly?month=3&year=2026&vehicle_id=3
Authorization: Bearer <access_token>
```

```json
{
  "month": 3,
  "year": 2026,
  "vehicle_id": 3,
  "total_days": 2,
  "total_km": 110,
  "rows": [
    {
      "date": "2026-03-01",
      "start_km": 152000,
      "end_km": 152060,
      "total_km": 60
    },
    {
      "date": "2026-03-02",
      "start_km": 152060,
      "end_km": 152110,
      "total_km": 50
    }
  ]
}
```

## Run Backend

```bash
pip install -r requirements.txt
cp .env.example .env
createdb tripmate_db
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Run Mobile Apps

```bash
cd mobile_app
flutter pub get
flutter run -t lib/main_driver.dart
flutter run -t lib/main_transporter.dart
```

Set API base URL in `mobile_app/lib/core/constants/api_constants.dart`.
