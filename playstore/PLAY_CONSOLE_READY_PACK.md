# TripMate Play Console Ready Pack

Last prepared: March 20, 2026

This pack gives you copy-ready material for:

- `TripMate Driver`
- `TripMate Transporter`

Before submission, replace any `REPLACE_ME` values with your final business details.

---

## 1) Core App Details

### TripMate Driver

- App name: `TripMate Driver`
- Package name: `com.tripmate.driver`
- Default language: `en-US`
- App type: `App`
- Category: `Business`
- Tags: `fleet`, `driver`, `trip tracking`, `fuel`, `attendance`
- Privacy policy URL: `https://13-60-219-105.sslip.io/privacy-policy/`
- Account deletion URL: `https://13-60-219-105.sslip.io/account-deletion/`

### TripMate Transporter

- App name: `TripMate Transporter`
- Package name: `com.tripmate.transporter`
- Default language: `en-US`
- App type: `App`
- Category: `Business`
- Tags: `fleet`, `transporter`, `vehicle tracking`, `reports`, `billing`
- Privacy policy URL: `https://13-60-219-105.sslip.io/privacy-policy/`
- Account deletion URL: `https://13-60-219-105.sslip.io/account-deletion/`

---

## 2) Store Listing Text

### TripMate Driver

**Short description**

`Trip tracking, fuel entry, attendance, tower diesel logs and live driver alerts.`

**Full description**

`TripMate Driver is built for fleet drivers who need a simple daily workflow for trip operations, odometer updates, fuel entries, and live trip monitoring.

With TripMate Driver, drivers can:

- Start Day with vehicle, service, odometer, and live location capture
- Record fuel filling entries with quantity, rate, and receipt/photo support
- Enter tower diesel filling logs when the transporter enables that module
- View tower sites on map and plan navigation to diesel locations
- End Day with closing odometer validation and trip completion checks
- Receive transporter and admin alerts directly in the app
- View trip history and previous runs

TripMate Driver also supports live trip tracking for active runs. When a trip is open, location can continue updating in the background so authorized fleet staff can monitor the current trip and route progress.

TripMate is designed for operational fleet use by approved transport companies and their assigned drivers.`  

### TripMate Transporter

**Short description**

`Manage drivers, vehicles, trips, live tracking, reports, diesel logs and bills.`

**Full description**

`TripMate Transporter helps fleet operators manage vehicles, drivers, attendance, trips, diesel logs, reports, and monthly billing from one place.

With TripMate Transporter, you can:

- View vehicles, drivers, services, and trip activity in one dashboard
- Monitor live driver trip routes on map
- Track attendance, daily runs, and open-trip status
- Review fuel records and tower diesel module entries
- Generate monthly reports and billing documents
- Create vehicle bill PDFs for transporter billing workflows
- Receive operational alerts and reminders in real time

TripMate Transporter is intended for authorized transporter and fleet management users. It works together with the TripMate Driver app to provide live fleet visibility and operational control.`  

---

## 3) Graphic Asset Checklist

Prepare these for **both apps**:

- App icon: `512 x 512`
- Feature graphic: `1024 x 500`
- Phone screenshots: at least `4`
- Optional tablet screenshots if available

### Screenshot plan: TripMate Driver

1. Login screen
2. Driver dashboard
3. Start Day screen
4. Fuel entry screen
5. Tower diesel screen
6. Trip history screen

### Screenshot plan: TripMate Transporter

1. Login screen
2. Transporter dashboard
3. Trips screen
4. Live tracking map screen
5. Reports screen
6. Vehicle bill PDF screen

---

## 4) Contact Details

Use the same support identity across both listings.

- Support email: `REPLACE_ME`
- Website: `REPLACE_ME`
- Phone: `REPLACE_ME`

If you do not yet have a public website, keep the privacy policy and account deletion URLs live on your current backend domain.

---

## 5) App Access For Reviewers

Google Play review will need working login access.

Create and provide:

- `Driver demo username/email`
- `Driver demo password`
- `Transporter demo username/email`
- `Transporter demo password`

### Reviewer notes for App Access

Paste this into Play Console:

`The app requires login. Please use the demo accounts below.

Driver app demo:
- Username/Email: REPLACE_ME
- Password: REPLACE_ME

Transporter app demo:
- Username/Email: REPLACE_ME
- Password: REPLACE_ME

If OTP or backend reset is needed, contact: REPLACE_ME`

---

## 6) Data Safety Draft

Use this as your answer guide in Play Console. Final answers must match real production behavior.

### TripMate Driver

**Data collected**

- Personal info:
  - email address
  - phone number
  - username
- Photos and videos:
  - odometer photos
  - uploaded fuel or logbook photos
- App activity:
  - trip records
  - attendance actions
  - diesel and fuel log usage
- Location:
  - precise location
  - background location during active trips
- Device or other IDs:
  - push notification token

**Data shared**

- No sale of data
- Operational data is shared only with the assigned transporter/admin inside the service

**Security**

- Data is transmitted over HTTPS in production
- App requires authenticated login for protected data

**Purpose examples**

- App functionality
- Account management
- Analytics / operational reporting
- Fraud prevention / safety / compliance
- Notifications

### TripMate Transporter

**Data collected**

- Personal info:
  - email address
  - phone number
  - username
  - company name
- Photos and videos:
  - billing logo uploads
  - logbook or proof uploads if used
- App activity:
  - trip management
  - fuel and diesel logs
  - reports and billing activity
- Location:
  - viewed live route data from drivers
- Device or other IDs:
  - push notification token

**Data shared**

- No sale of data
- Data is used inside the fleet-management service only

**Security**

- Data is transmitted over HTTPS in production
- Authenticated access required

---

## 7) Content Rating Guidance

Most likely selection:

- Category: `Business`
- No gambling
- No sexual content
- No graphic violence
- No drugs encouragement
- No public social sharing

Expected result: low maturity / general business-use rating.

---

## 8) Driver Background Location Declaration

This section is for **TripMate Driver only**.

### Why background location is needed

Paste/adapt this:

`TripMate Driver is used by fleet drivers during active vehicle runs. The app must continue collecting location while a trip is open so authorized transporter and fleet admin users can monitor route progress, detect trip status, review actual movement, and maintain trip records even when the driver minimizes or closes the app during work. Tracking is intended only for active operational trips and should stop once the trip is ended.`

### In-app disclosure summary

Paste/adapt this:

`TripMate uses location while a trip is open to monitor the active run, show live trip status to authorized fleet staff, and record route history. On Android, this may continue when the app is minimized or closed until the trip is ended.`

### Video demo checklist

Record a short review video showing:

1. Driver logs in
2. Start Day
3. Disclosure dialog appears
4. User grants location permission
5. Open trip remains active
6. App is minimized / removed from foreground
7. Transporter app shows live trip on map
8. End Day stops the trip

---

## 9) Closed Testing Plan For Personal Developer Account

If Google requires closed testing for your personal account:

- Minimum testers: `12`
- Minimum duration: `14 continuous days`

### Tester invite message

`Hi, please help test TripMate on Google Play Closed Testing.

Apps:
- TripMate Driver
- TripMate Transporter

What to test:
- Login
- Start Day / End Day
- Trip creation
- Fuel entry
- Live tracking
- Notifications
- Reports / billing

Please install from the Play testing link and use the app during the test period.`

---

## 10) Release Notes

### TripMate Driver

`Initial Play release with Start Day / End Day workflow, fuel entry, trip history, live trip alerts, tower diesel support, and active trip location tracking.`

### TripMate Transporter

`Initial Play release with driver and vehicle management, live trip tracking, fuel and diesel records, monthly reports, and vehicle bill PDF generation.`

---

## 11) Final Manual Checklist

- [ ] Upload keystore created and stored safely
- [ ] `mobile_app/android/key.properties` filled
- [ ] Driver `.aab` built
- [ ] Transporter `.aab` built
- [ ] Privacy policy page deployed and public
- [ ] Account deletion page deployed and public
- [ ] Demo accounts created
- [ ] Screenshots captured
- [ ] Data safety form completed
- [ ] Driver background location declaration submitted
- [ ] Closed test created if required
- [ ] Production rollout requested after testing approval

---

## 12) Important URLs

- Privacy policy: `https://13-60-219-105.sslip.io/privacy-policy/`
- Account deletion: `https://13-60-219-105.sslip.io/account-deletion/`
- Driver package: `com.tripmate.driver`
- Transporter package: `com.tripmate.transporter`
