# Mobile / LAN access (W25)

Reach the Whisper dashboard from a phone on the same Wi-Fi over HTTPS, with
camera capture and fragment upload working from the LAN origin.

The default remains loopback-only. Nothing here changes that until
`ZMI_LAN_ACCESS=true` is set explicitly.

## Prerequisites

- The dashboard runs on the host machine.
- The phone is on the same Wi-Fi/LAN as that machine.
- The `cryptography` package is installed (`pip install cryptography`) for
  certificate generation.

## 1. Enable LAN mode

Edit `scan_config.env`:

```
ZMI_LAN_ACCESS=true
DASHBOARD_HOST=0.0.0.0
ZMI_LAN_HOSTS=whisper.local
DASHBOARD_PORT=5001
```

- `ZMI_LAN_ACCESS=true` is the explicit opt-in. Without it,
  `DASHBOARD_HOST=0.0.0.0` is rejected at startup.
- `DASHBOARD_HOST=0.0.0.0` binds every interface. A specific LAN IP is not an
  accepted bind value.
- `ZMI_LAN_HOSTS` lists extra hostnames/IPs to accept in the Host/Origin check
  and to write into the certificate SAN. Detected private LAN IPs are added
  automatically.

## 2. Generate the local HTTPS certificate

```
python scripts/setup_lan_certificate.py
```

This writes three files under `<DATA_ROOT>/lan-access/` (`lan-access/` is
gitignored — never commit the key):

| File | Purpose |
|---|---|
| `dashboard-lan-ca.pem` | Local root CA. Install this on the phone. |
| `dashboard-lan-cert.pem` | Server certificate (SAN = hosts + LAN IPs). |
| `dashboard-lan-key.pem` | Server private key. Keep secret. |

The command prints the paths, the server certificate SHA-256 fingerprint, the
CA fingerprint, the SAN list, and the phone URLs.

## 3. Point the dashboard at the certificate

```
DASHBOARD_CERT=<DATA_ROOT>/lan-access/dashboard-lan-cert.pem
DASHBOARD_KEY=<DATA_ROOT>/lan-access/dashboard-lan-key.pem
```

Set both or neither. Setting only one is a configuration error.

## 4. Start and open on the phone

Start the dashboard as usual. It binds `0.0.0.0` and serves HTTPS.

Open the phone URL printed by step 2, for example:

```
https://192.168.1.50:5001/
```

The dashboard must be served over HTTPS for the browser camera permission.

## 5. Trust the certificate on the phone

The certificate is locally generated, so the phone must trust the local CA
first. HTTPS/camera will not work otherwise.

- **Android**: Settings -> Security -> Encryption & credentials -> Install a
  certificate -> CA certificate -> pick `dashboard-lan-ca.pem`. The file is a
  root CA; name it "Whisper LAN".
- **iOS**: transfer `dashboard-lan-ca.pem` to the phone, install the profile
  (Settings -> General -> VPN & Device Management), then enable it under
  Settings -> General -> About -> Certificate Trust Settings.

Verify the installed certificate fingerprint matches `ca-fingerprint-sha256`
from step 2 before trusting it.

## Security model

- Loopback remains the default. LAN mode is explicit opt-in.
- The Host header must match an allowed hostname (loopback, configured hosts,
  detected LAN IPs). Other hosts get `403`.
- Mutating requests also require a same-origin `Origin` and the per-process
  `X-Local-Dashboard-Token`.
- The private key is gitignored and never printed.
- Detected URLs are built from real LAN addresses; no application URL is
  hardcoded to loopback.

## Validation

```
python scripts/gate_runner.py targeted tests/test_lan_access.py
python scripts/gate_runner.py targeted tests/test_dashboard_lan_access.py
python scripts/gate_runner.py targeted tests/integration/test_lan_https_server.py
```

Playwright HTTPS journey (report: `mobile_lan_access_report.json`):

```
set ZMI_BASE_URL=https://<lan-ip>:<port>
set ZMI_EXPECT_LAN=1
python tests/e2e/mobile_lan_access.py
```

## Troubleshooting

- **Camera blocked**: the page must be loaded over `https://`, not `http://`.
- **Browser certificate warning**: install the local CA on the device (step 5).
- **`403` from the phone**: add the phone's URL host to `ZMI_LAN_HOSTS`.
- **`DASHBOARD_HOST must be a loopback address`**: set `ZMI_LAN_ACCESS=true`.
- **Local CA trust cannot be verified on the host**: some security suites
  (for example Norton Web/Mail Shield) intercept local TLS and replace the
  served certificate. Trust cannot be evaluated while that interception is
  active; disable it or validate the certificate on the phone. The offline
  chain test in `tests/test_lan_access.py` still proves the CA -> server cert
  relationship.
