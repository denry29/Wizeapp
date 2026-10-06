# TravelWise - Trip Planner (Flask + SQLite + Expo)

A mobile-friendly Flask web application with an Expo (React Native) client
that also runs in Chrome through Expo Web. Users can browse a curated catalogue
of **300 photo-backed Asian destinations**, plan trips and itineraries, record
planned and actual expenses, and manage notes and packing checklists.

Built as a third-year Computer Science project to demonstrate layered
architecture and the four principles of object-oriented programming.

---

## 1. Technology stack

| Concern | Choice |
|---|---|
| Language | Python 3.9+ |
| Web framework | Flask 3 |
| Database | SQLite (standard-library `sqlite3` module — **no ORM**) |
| Password hashing | Werkzeug (`pbkdf2:sha256`) |
| Sessions | Flask signed-cookie sessions |
| Mobile/web client | React Native + Expo + Expo Web |
| Tests | pytest |

The existing Flask/Jinja web application remains available. The separate Expo
client calls the Flask REST API; it does not replace or bundle the Flask site.

---

## 2. Quick start (Windows + VS Code)

Run every command from the project root in the VS Code terminal.

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install the dependencies
python -m pip install -r requirements.txt

# 3. Create the database and load the curated 300 destinations
python scripts\init_db.py --seed

# 4. (optional) create a demo account with sample data
python scripts\create_demo_user.py --with-samples

# 5. Run the application
python app.py
```

Then open **<http://127.0.0.1:5000>** in your browser.

If PowerShell blocks the activation script, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Run the React Native client in Chrome (Expo Web)

In a second terminal, from the project root:

```powershell
npm.cmd install
npx.cmd expo start --web
```

Open the Expo Web URL (normally **<http://localhost:8081>**) in Chrome.
Expo Web uses the same React Native screens/components as the mobile client.
Set the Expo-only public API address in `.env.local` (which is git-ignored):

```powershell
Set-Content .env.local 'EXPO_PUBLIC_API_URL=http://localhost:5000'
npx.cmd expo start --web
```

### Run Expo Go on a physical Android phone

The native client does not assume that `localhost` or the Android-emulator-only
`10.0.2.2` address is reachable from a phone. Find your computer's LAN IPv4
address (for example with `ipconfig`), keep the phone and computer on the same
network, and start Expo with the backend's LAN URL:

```powershell
# Terminal 1 - Flask listens on 0.0.0.0:5000 by default
python app.py

# Terminal 2
Set-Content .env.local 'EXPO_PUBLIC_API_URL=http://192.168.100.37:5000'
npx.cmd expo start
```

Allow Python/port 5000 through Windows Firewall on the private network if
prompted. Use `http://10.0.2.2:5000` only when the app is running in an Android
emulator. Replace `192.168.100.37` if the computer's LAN address changes.
`.env.local` must contain only Expo client settings such as
`EXPO_PUBLIC_API_URL`; Expo deliberately reads these files into the client
build.

For browser cookie authentication, Flask allows the default Expo development
origins on ports 8081 and 19006. Add other origins to `EXPO_WEB_ORIGINS` in
`.backend.env` if needed. Keep the Flask API running while testing the Expo app.

### Verify it works

```powershell
# API health check (status "ok" and 8 tables)
Invoke-WebRequest http://127.0.0.1:5000/health | Select-Object -ExpandProperty Content

# Browse the catalogue without signing in
Invoke-WebRequest "http://127.0.0.1:5000/api/destinations?country=Japan&per_page=3"
```

### Demo account

`scripts\create_demo_user.py` prints the credentials it creates:

* e-mail: `demo@wize.local`
* password: `DemoPass123!`

> These are **development-only** credentials. Set `WIZE_DEMO_PASSWORD`
> in the environment before sharing the project.

---

## 3. Project structure

```text
TravelWise/
├── app.py                    # application factory + blueprint registration
├── config.py                 # environment configuration and domain constants
├── requirements.txt  .env.example  .gitignore  README.md
├── App.js                    # Expo / React Native client (also Expo Web)
├── app.json  package.json    # Expo app and JavaScript dependencies
│
├── database/
│   ├── db.py                 # DatabaseManager - all SQL connection handling
│   ├── schema.sql            # tables, constraints, indexes
│   └── wize.db               # created by scripts/init_db.py (git-ignored)
│
├── models/                   # domain entities (data + behaviour)
│   ├── base.py               # BaseModel (abstract)
│   ├── user.py  trip.py  destination.py
│   ├── schedule.py  expense.py  checklist.py
│
├── managers/                  # business rules + SQL (one per feature)
│   ├── base_manager.py        # BaseManager (abstract, generic CRUD)
│   ├── auth_manager.py  trip_manager.py  destination_manager.py
│   ├── schedule_manager.py  expense_manager.py  checklist_manager.py
│   └── dashboard_manager.py
│
├── routes/                    # Flask blueprints - HTTP layer only
│   ├── auth_routes.py  trip_routes.py  destination_routes.py
│   ├── schedule_routes.py  expense_routes.py  checklist_routes.py
│   ├── mobile_routes.py       # favorites, notes, saved options, travel search
│   └── dashboard_routes.py
│
├── services/                  # cross-cutting concerns
│   ├── validation.py          # all server-side input validation
│   └── security.py            # CSRF tokens, login guards, error translation
│
├── static/
│   ├── css/style.css          # mobile-first responsive stylesheet
│   ├── js/app.js              # CSRF helper + small UI behaviours
│   ├── img/wize.png           # MASTER logo (1482x1062, transparent bg)
│   ├── favicon.ico            # 16/32/48 frames, rounded corners, browser tab
│   ├── favicon-32.png         #   "
│   ├── apple-touch-icon.png   # 180x180 opaque PNG for iOS home screen
│   ├── icon-192.png           # Android launcher / PWA
│   ├── icon-512.png           #   "
│   ├── icon-maskable-512.png  # Android adaptive icon (inside the safe zone)
│   ├── logo-160.png           # header logo, natural aspect, boxed at 40 CSS px
│   └── manifest.webmanifest   # PWA metadata: app name, theme colour, icons
│
├── templates/                 # Jinja2 templates, all extending base.html
│
├── data/asia_destinations.json  # curated 300 photo-backed destinations
│
├── scripts/                   # one-off maintenance commands
│   ├── init_db.py  seed_destinations.py  create_demo_user.py
│   └── make_icons.ps1         # rebuilds every icon from static/img/wize.png
│
└── tests/                     # 228 automated tests
```

---

## 4. Database design

```
users 1───n trips ───n trip_destinations n───1 destinations
                │                            │
                ├──n schedules ──(optional)──┘
                ├──n expenses
                └──n checklists ───n checklist_items
```

* `PRAGMA foreign_keys = ON` is set on **every** connection, so `ON DELETE
  CASCADE` really fires.
* `CHECK` constraints enforce allowed statuses, positive amounts, valid
  categories and `end_date >= start_date` at the database level.
* `destinations.name_key` is a normalised name (`Kinkaku-ji` → `kinkaku ji`)
  with `UNIQUE (name_key, country, city)`, which makes the catalogue
  duplicate-proof *and* the seeder idempotent.
* `destinations` also stores user-created spots (`is_custom = 1`,
  `user_id` → owner), so personal entries stay separate from the shared
  catalogue and are only visible to their owner.

---

## 5. Where each OOP principle is applied

| Principle | Where |
|---|---|
| **Abstraction** | `models/base.py` → `BaseModel(ABC)` with abstract `from_row()` / `serialize()`. `managers/base_manager.py` → `BaseManager(ABC)` with abstract `_to_model()`. |
| **Inheritance** | `User`, `Trip`, `Destination`, `Schedule`, `Expense`, `Checklist` all extend `BaseModel`; the seven managers extend `BaseManager`. |
| **Polymorphism** | Each manager overrides `table`, `primary_key`, `owner_column` and `model`, so one generic `create/get_by_id/update/delete` implementation yields seven different behaviours. `Destination.from_row()` returns a `Destination` **or** a `CustomDestination` depending on the row. |
| **Encapsulation** | `DatabaseManager` owns the connection lifecycle; `AuthManager` hashes passwords so no route ever sees a hash; managers expose intent-named methods (`attach_to_trip`, `budget_status`) instead of SQL; models expose read-only properties. |
| **Composition** | `Checklist` owns its `ChecklistItem` objects and derives progress; `DashboardManager` composes the other managers so every number is filtered by the same ownership rules. |

---

## 6. API reference (JSON)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create an unverified account and send a verification code |
| POST | `/api/auth/verify-email` | Verify an account with its 6-digit code |
| POST | `/api/auth/resend-verification` | Resend a code subject to a cooldown |
| POST | `/api/auth/login` | Sign in only after email verification |
| POST | `/api/auth/logout` | Sign out |
| GET | `/api/auth/me` | Current user |
| GET | `/api/auth/csrf` | CSRF bootstrap for the Expo client |
| GET | `/api/dashboard` | Overview for the signed-in user |
| GET / POST | `/api/trips` | List / create trips |
| GET / PUT / PATCH / DELETE | `/api/trips/<id>` | One trip |
| GET | `/api/destinations?search=&country=&city=&category=&page=` | Browse catalogue |
| GET | `/api/destinations/filters` | Countries / categories / cities |
| GET | `/api/destinations/<id>` | Destination detail |
| GET / POST | `/api/trips/<id>/destinations` | List / attach destinations |
| PATCH / DELETE | `/api/trips/<id>/destinations/<link_id>` | Edit / detach |
| GET / POST | `/api/trips/<id>/schedules` | List / add activities |
| GET / PUT / PATCH / DELETE | `/api/schedules/<id>` | One activity |
| GET / POST | `/api/trips/<id>/expenses` | List / add expenses |
| GET | `/api/trips/<id>/expenses/summary` | Totals, per-category, **budget** |
| GET / PUT / PATCH / DELETE | `/api/expenses/<id>` | One expense |
| GET / POST | `/api/trips/<id>/checklists` | List / create checklists |
| GET / PUT / PATCH / DELETE | `/api/checklists/<id>` | One checklist |
| GET / POST | `/api/checklists/<id>/items` | List / add items |
| PUT / PATCH / DELETE | `/api/checklist-items/<id>` | Edit / delete item |
| POST | `/api/checklist-items/<id>/toggle` | Tick / untick item |
| GET / POST / DELETE | `/api/favorites` and `/api/favorites/<destination_id>` | User-owned favorites |
| GET / POST | `/api/trips/<id>/notes` | List / add trip notes |
| PUT / PATCH / DELETE | `/api/notes/<note_id>` | Edit / delete an owned note |
| GET / POST | `/api/trips/<id>/saved-options` | List / save a flight or hotel option |
| DELETE | `/api/saved-options/<option_id>` | Remove a saved option |
| GET | `/api/hotels/search` | StayingAPI live hotel offers in Asian destinations |
| GET | `/api/hotels/reviews` | On-demand real reviews for a hotel result |

Every mutating request needs the CSRF token, sent either as the
`X-CSRF-Token` header or a `csrf_token` form/JSON field.

### Account registration, verification, and login

Copy `.env.example` to `.backend.env` and configure a real SMTP account on the
Flask server before testing registration. Keep this file server-only; Expo
must not load it. The service uses Python's standard-library
SMTP client; the email host, port, sender, optional credentials, and TLS
settings are read only by the backend. No email provider or SMTP credentials
are bundled with this project. Registration will remain pending if email
delivery is unavailable; configure SMTP and use the resend action to receive a
working code.

The server creates a six-digit random code with a 10-minute lifetime. It
stores only an HMAC-SHA256 digest, allows at most six incorrect attempts, and
deletes the code after successful verification. Resends replace the prior code
and are limited to one per account every 60 seconds. Passwords are stored as
Werkzeug PBKDF2-SHA256 hashes. Unverified accounts cannot sign in. Successful
sign-ins update `users.last_login_at`, append minimal device/client metadata
to `login_history` (without saving IP/location), and send a security email.
If that notification cannot be delivered, authentication remains successful
and the API reports a warning.

For local email testing, use an SMTP sandbox/provider account rather than
committing credentials. Set a stable, high-entropy `WIZE_SECRET_KEY` before
deployment; changing it invalidates existing signed-cookie sessions and
verification-code digests. Use HTTPS in production. For a complete
registration test, start Flask with SMTP configured, create an account from
the Expo app or `/auth/register`, enter the received code, then sign in. The
test suite uses an in-memory mail outbox and does not send real email.

The native Expo app uses the Flask signed session cookie and the existing
CSRF-protected JSON API; it does not contain database, email, StayingAPI, or
secret-key credentials. Flask loads backend settings from the ignored
`.backend.env`; Expo loads its public API URL from the ignored `.env.local`.
Never put backend secrets in `EXPO_PUBLIC_*` variables.

---

## 7. Security

* Passwords hashed with PBKDF2-SHA256; never stored or returned in plain text.
* All SQL uses parameterised queries (`?` placeholders) — no SQL is built from
  user input.
* Ownership is enforced in the manager layer, so changing an id in a URL gives
  `404` (never `403`, which would confirm the record exists).
* CSRF protection on every `POST/PUT/PATCH/DELETE` (custom implementation, no
  extra dependency).
* Session cookie is `HttpOnly` + `SameSite=Lax`; `Secure` in production.
* Security headers: `X-Frame-Options`, `X-Content-Type-Options`, CSP.
* The secret key is never hard-coded: it comes from `WIZE_SECRET_KEY` or
  is generated into `.secret_key` (both git-ignored).
* New accounts must verify email before login. Verification codes are
  short-lived, single-use HMAC digests; login and resend attempts are
  rate-limited.
* SMTP credentials are backend-only environment settings. Login notifications
  are sent only after successful authentication; IP addresses and guessed
  locations are not stored or included.

---

## 8. Tests

```powershell
python -m pytest tests -q
```

Tests cover registration/login, CSRF, trip CRUD and validation, destination
search/filtering, favorites, notes, saved travel options, itinerary rules,
planned-versus-actual expense totals and budgets, checklist progress,
unauthorised access, database constraints and cascades, the exact 300-record
dataset, and the existing Flask web app.

Each test gets its **own temporary database file**, so the real
`wize.db` is never touched by the test run.
---

## 9. The destination dataset

`data/asia_destinations.json` contains **exactly 300 unique destinations
across 33 Asian countries**. Each selected destination has an HTTPS photo and
Commons creator, source-page, licence, and attribution details. The catalogue
contains no invented images or image URLs. The Philippine exception remains
supported by the seeder, but the current curated 300 all have photos.

Run the seeder at any time — it is safe to repeat:

```powershell
python scripts\seed_destinations.py            # insert what is missing
python scripts\seed_destinations.py --check    # validate only, write nothing
python scripts\seed_destinations.py --min 300  # require N verified records
```

It prints how many records were valid, inserted, skipped and rejected, and
publishes exactly 300 catalogue rows. Older catalogue rows in an existing
database are hidden from new searches rather than deleted, so previously
saved trip destinations are preserved. It exits with status `1` if the data
does not contain exactly 300 valid unique records. It **never** invents rows.

#### Destination photos (Wikimedia Commons)

`scripts/fetch_destination_images.py` attaches a freely-licensed photo to each
catalogue destination. It searches Commons with the destination's name **and**
city **and** country, then scores every hit before accepting one:

| Score component | Weight | Meaning |
|---|---|---|
| All name tokens present | +0.6 | scaled down proportionally on a partial match |
| City appears in the file title | +0.2 | confirms the right location |
| Country appears in the file title | +0.1 | weak extra signal |
| **No** name token overlap | hard 0.0 | rejected outright as unrelated |

The default `--min-score` is **0.75**, so a name-only match (max 0.6) is never
accepted automatically. Only candidates whose licence is clearly free
(CC / public domain) are eligible, and only JPEG/PNG files are embedded.

```powershell
python scripts\fetch_destination_images.py --report-only   # counts, no network
python scripts\fetch_destination_images.py --dry-run      # search, write nothing
python scripts\fetch_destination_images.py --limit 25      # try a small batch
python scripts\fetch_destination_images.py                # fetch what is missing
python scripts\fetch_destination_images.py --retry-errors # re-try failed rows
```

The run **is resumable**: every processed destination gets a row in the
`destination_images` ledger (`matched` / `review` / `no_result` / `error`), so
re-running only searches what is still missing. Destinations that already have
a real `image_url` are skipped without a network call, and no name, fee,
currency or description is ever modified.

Anything uncertain is recorded as `review` and left **without** an image rather
than guessed at — the browse page keeps showing its existing placeholder. Each
matched image stores its title, creator, source page, licence and licence URL,
which the templates render as a visible credit line under the photo.

The script is polite by design: a descriptive `User-Agent`, ~3 requests/second,
and exponential backoff on `429`/`5xx`.

Entrance fees, best times, recommended duration, and coordinates are provided
only when available; otherwise those fields remain blank rather than guessed.
To regenerate the 300-entry data file from the existing Commons image library,
run `python scripts\curate_destination_dataset.py` after the database has been
seeded and image records have been populated.

## Flight and hotel search

Hotel search is available at `/hotels` and is proxied server-side to
[StayingAPI](https://stayingapi.com/docs) through `/api/hotels/search`;
real detailed reviews are fetched only when a user opens a hotel's review
section. Set `STAYING_API_KEY` in `.backend.env` or provide it in the
deployment environment. The key is used only by Flask and is never sent to
browser code or loaded by Expo. Flask sends it as an
`Authorization: Bearer <key>` header. Live keys also require the StayingAPI
account email to be verified (a one-click link sent at signup); until then
the provider returns `email_unverified` and the UI explains the next step.
Live searches may complete asynchronously,
so Flask polls the provider's job endpoint until the result is ready.

Hotel searches accept an Asian country/region, city, dates, adults, rooms, and
optional children/ages. Images, ratings, review counts, amenities, policies,
availability, and prices are displayed only when StayingAPI returns them.
StayingAPI's documented `Property.images` field is a list of image URI
strings; each result URL is passed through unchanged to Expo's hotel image
component. Missing or unreachable images use the local "Photo not available"
fallback. The image CDN request is made directly by the client and does not
send the StayingAPI key.
Provider totals and currencies are preserved without recalculation or foreign
exchange conversion. Adding a priced hotel saves it as a hotel option and
creates a linked planned hotel expense using the provider's official stay
total; flight and hotel options use separate planned expense categories, and
removing an option also removes its linked estimate. Planned and
actual trip costs remain separate and are summarized per currency.

The seeder publishes exactly 300 shared catalogue rows. It marks superseded
shared rows unlisted rather than deleting them, because old trip destinations
can still reference those rows. This preserves existing trip data while all
catalogue searches return the exact curated set.

---

## 10. Testing on an Android phone over USB (ADB)

1. Enable **Developer options → USB debugging** on the phone and connect it
   by USB (accept the "Allow USB debugging?" prompt).

2. Install ADB and confirm the device is seen:

   ```powershell
   adb devices
   ```

3. Run the app and forward the port:

   ```powershell
   python app.py
   adb reverse tcp:5000 tcp:5000
   ```

4. On the phone open **<http://127.0.0.1:5000>** in Chrome. The CSS is
   mobile-first, so the layout adapts to the phone screen.

5. To undo the forwarding:

   ```powershell
   adb reverse --remove tcp:5000
   ```

> `adb reverse` makes the phone treat `127.0.0.1:5000` as *your* computer, so
> the same URL works on both. If port 5000 is taken, set `PORT=5050` and
> forward `tcp:5050` instead.

---

## 11. The logo on your phone

The master artwork is **`static/img/wize.png`** (1482×1062, transparent
background). Everything else is generated from it, so the logo only ever has to be
replaced in that one file.

It is **not** a square — the mark is wider than it is tall — so every icon is
fitted to the artwork's real aspect ratio rather than squashed into a square
canvas. `scripts/prepare_logo.ps1` produced this file from the original flat
image: it knocks out the white background *without* touching the white
highlights inside the mark, recovers the anti-aliased edges, trims the empty
margin and writes a 32-bit PNG.

Phones do not read the 1482×1062 master PNG directly — each surface needs its own
size, which is why the build produces several files:

| Surface | File | Size |
|---|---|---|
| Browser tab (desktop) | `static/favicon.ico` | 16 / 32 / 48, rounded corners |
| Browser tab (mobile) | `static/favicon-32.png` | 32 |
| iOS "Add to Home Screen" | `static/apple-touch-icon.png` | 180, **opaque** |
| Android launcher / PWA | `static/icon-192.png`, `icon-512.png` | 192, 512 |
| Android adaptive icon | `static/icon-maskable-512.png` | 512, artwork inside the 80% safe zone |
| In-app header | `static/logo-160.png` | 160 wide, natural aspect, fitted (`object-fit: contain`) inside a 40 CSS px rounded box |

The master carries a real **alpha channel**, so its background is transparency
rather than a flat colour, and after trimming the artwork fills **90%** of the
width and **94%** of the height of the canvas (1338×1003 of 1482×1062).
`make_icons.ps1` locates that box with `Get-ContentBounds` and builds every icon
from it, which is what keeps the empty space down. Two details follow from the
alpha channel:

* `Get-ContentBounds` has to test **alpha before colour**. A transparent pixel
  stores `R=G=B=0`, which its "distance from white" test reads as *maximally*
  far from white — without the alpha guard the whole canvas is mistaken for
  artwork and every icon comes out nearly empty.
* The **maskable icon's** padding colour is sampled from the master's corner.
  An alpha master has no colour there, so the script falls back to white;
  otherwise the transparent corner would paint the Android adaptive icon black.

It then uses a **contain** fit: the logo is made as large as
the canvas allows and is never cropped, so it spans the full width of a square
icon and leaves only slim bands top and bottom.

`apple-touch-icon.png` is written as a **24-bit PNG with no alpha channel**,
because iOS renders any transparency as solid black. The maskable icon keeps the
artwork inside the 80% safe zone so a circular or squircle launcher mask cannot
crop it, and its padding is filled with the logo's own corner colour so the border
blends in.

The two **browser-tab** files are the opposite case: they are built with `-Rounded`,
which clips the canvas to a rounded square and leaves the corners **transparent**.
A tab draws the icon on its own chrome, so a white corner would read as a hard
square again — the transparency is what makes the curve show. The PWA and iOS
icons stay square on purpose, because those launchers apply their own mask and a
curve baked into the file would be doubled up or clipped away.

### Changing the logo

1. Replace `static/img/wize.png`. A PNG with a transparent background is
   best — the generator reads its alpha channel and trims the empty margin.
   A flat white background also works; run `scripts\prepare_logo.ps1` first to
   strip it.
2. Rebuild every icon:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\make_icons.ps1
   ```

   The script uses the `System.Drawing` API that ships with Windows, so **no
   extra Python package is needed**. To build from a file elsewhere:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\make_icons.ps1 -Source C:\pictures\logo.png
   ```

3. Hard-refresh the browser (icons are cached aggressively): `Ctrl` + `F5`.

### Seeing it on the phone

`app.py` already binds to `0.0.0.0`, so the phone can reach the dev server over
Wi-Fi. Either follow the ADB steps in section 10, or use your machine's LAN IP,
for example **<http://192.168.1.5:5000>**.

To put the logo on the **home screen**:

* **Android (Chrome)** — menu → *Add to Home screen*. The name, icon and status
  bar colour come from `manifest.webmanifest` and the `theme-color` meta tag.
* **iPhone (Safari)** — Share → *Add to Home Screen*. iOS uses
  `apple-touch-icon.png` and `apple-mobile-web-app-title`.

Both open the app full-screen (`display: standalone`) with the brand-coloured
status bar. The manifest is served from `/manifest.webmanifest` by a small route
in `app.py`, because Python's `mimetypes` does not recognise the
`.webmanifest` extension on every platform.

> Icons are cached hard by phones and browsers. If the home-screen icon still
> shows the old image, delete the shortcut, clear the browser cache for the site
> and add it again.

---

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Add Python to `PATH`, or reinstall with "Add to PATH" ticked. |
| `Activate.ps1` is blocked | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `Address already in use` | `$env:PORT=5050; python app.py` |
| Empty destination list | `python scripts\init_db.py --seed` |
| Want to start over | `python scripts\init_db.py --reset --seed` |
| CSRF error on a JSON call | Send `X-CSRF-Token` with the token from the page |

---

## 13. Scope

Deliberately **not** included: flight/hotel/transport booking, payments, live
GPS, real-time weather, collaboration, or AI-generated itineraries. The focus
is personal trip planning, destination browsing, schedules, expenses and
checklists.
