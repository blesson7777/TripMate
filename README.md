# TripMate Fleet Management System

Full-stack fleet and transport management system with:

- Backend: Django + DRF + JWT + PostgreSQL
- Mobile: Flutter + Provider + Clean Architecture
- Admin Panel: Django Admin

## Backend structure

```text
tripmate/
  manage.py
  requirements.txt
  .env.example
  tripmate/
    settings.py
    urls.py
  users/
    models.py
    serializers.py
    views.py
    permissions.py
    urls.py
    admin.py
  vehicles/
    models.py
    serializers.py
    views.py
    urls.py
    admin.py
  drivers/
    models.py
    serializers.py
    views.py
    urls.py
    admin.py
  attendance/
    models.py
    serializers.py
    views.py
    urls.py
    admin.py
  trips/
    models.py
    serializers.py
    views.py
    urls.py
    admin.py
  fuel/
    models.py
    serializers.py
    views.py
    urls.py
    admin.py
  reports/
    views.py
    serializers.py
    urls.py
```

## Flutter structure

```text
mobile_app/
  pubspec.yaml
  lib/
    main.dart
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

## Core business implementation

- Driver must start attendance before adding trip/fuel.
- One attendance per driver per date.
- Trips and fuel records are linked to attendance.
- Odometer images stored in Django media (`/media/attendance`, `/media/fuel`).
- GPS latitude/longitude captured at attendance start.
- Monthly report provides date-wise trip sheet rows.

## API endpoints

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

## Sample API request/response

### 1) Login

Request:

```http
POST /api/login
Content-Type: application/json

{
  "username": "driver1",
  "password": "Password@123"
}
```

Response:

```json
{
  "refresh": "eyJ...",
  "access": "eyJ...",
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

### 2) Start attendance

Request (multipart):

```http
POST /api/attendance/start
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

start_km=152340
latitude=22.572645
longitude=88.363892
odo_start_image=<file>
```

Response:

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

### 3) Add trip

Request:

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

Response:

```json
{
  "id": 19,
  "attendance": 8,
  "start_location": "Kolkata Depot",
  "destination": "Howrah Yard",
  "start_km": 152340,
  "end_km": 152372,
  "total_km": 32,
  "purpose": "Material delivery"
}
```

### 4) Monthly report

Request:

```http
GET /api/reports/monthly?month=3&year=2026&vehicle_id=3
Authorization: Bearer <access_token>
```

Response:

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

## Run backend

```bash
pip install -r requirements.txt
cp .env.example .env
createdb tripmate_db
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Run mobile app

```bash
cd mobile_app
flutter pub get
flutter run
```

Set API base URL in `lib/core/constants/api_constants.dart`.
