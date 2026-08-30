# PRV Barcode Label Printer

A small internal web service for preparing and printing 50 × 30 mm product labels on the networked SATO CG412DT-LAN.

The site includes Android and iPad home-screen metadata and a green PRV Label Station icon in standard, maskable, and Apple touch sizes.

The operator can:

- enter a MYOB Advanced purchase-order number;
- review the order's inventory lines, selected by default;
- review purchase-order labels in natural item-code order by default, with MYOB line order still available;
- exclude lines or change label quantities;
- add item codes and quantities manually;
- enter existing manufacturer barcodes directly against active MYOB stock items; and
- print the item description, item code, and scannable Code 128 barcode.

The **Enter barcodes** tab shares the stored active-stock catalogue and manual MYOB refresh used by **Assign barcodes**, but does not require the administration PIN. Search or filter the list, tap an item, scan its existing manufacturer barcode, and add it to a batch before choosing **Send to MYOB**. Missing rows are created, `x` placeholders are treated as missing, and an existing single Barcode row can be deliberately replaced; products with multiple Barcode rows remain blocked for manual cleanup. Duplicate checks compare only MYOB cross-references whose `AlternateType` is `Barcode`, so the same value in a supplier, customer, or other cross-reference does not block entry. Each batch re-reads its selected items immediately before writing and reads them back afterward to verify MYOB stored the expected values. While that write and verification is running, a non-dismissible progress dialog freezes the rest of the UI and warns against closing the page. A partial failure leaves the browser batch intact so it can be refreshed and safely retried. Searches on both catalogue tabs split the query into words and require every word to match somewhere in the item code, description, or barcode, regardless of word order. The Enter barcodes list can also be limited to products with positive MAIN QtyOnHand whenever the shared 24-hour stock snapshot is valid. Both catalogue lists render 250 items initially, automatically add another 250 near the scroll boundary, and retain a **Load more** button as a manual fallback until every matching item is visible.

The **Check Barcode** tab listens for scanner input without requiring a field to be selected. Each scan replaces the previous result with the active MYOB item code, description, and vendor part number linked to that Barcode cross-reference. Supplier or customer cross-reference values are not treated as barcodes. An unlinked scan shows a clear warning and immediately leaves the page ready for the next product.

The **Enter barcodes** list also has a narrow **On hand** column for the `MAIN` warehouse. Stock on hand is a shared, stored snapshot in `data/barcode-stock-on-hand.json`: opening the tab or refreshing the product catalogue never triggers the slow stock request. The snapshot is valid for 24 hours and survives container restarts. Once it expires, stock values are hidden until an operator explicitly chooses **Refresh stock on hand**, refreshes it from **Manual Print**, or refreshes stock from the post-assignment label dialog. Manual Print can use the stored `MAIN` quantity directly as the requested label quantity.

The **Assign barcodes** tab is protected by a server-configured PIN. It loads active MYOB stock items for local code/description searching, shows each current Barcode cross-reference, previews generated internal EAN-13 values, rechecks the stored active-item snapshot for collisions, and then updates MYOB. The snapshot is stored in `data/barcode-stock-items.json`, survives container restarts, and changes only after a manual refresh or successful assignment. Concurrent refresh requests share one MYOB catalogue load. Review uses this local snapshot rather than downloading the catalogue again. Barcode numbers are allocated separately by a persistent, atomically locked high-water counter in `data/barcode-sequence.json`. Immediately before writing, confirmation reads only the selected items from MYOB so current Barcode row IDs are used; those items are read back again after writing for verification. An existing Barcode detail row—including an `x` placeholder—is deleted by its MYOB detail `id` and replaced in the same PUT; a new row is appended only when no Barcode row exists.

After a successful assignment, the operator can prepare labels for those items using the same stored `QtyOnHand` snapshot for the `MAIN` warehouse. A fresh snapshot opens the normal label review immediately without contacting MYOB. If it is missing or more than 24 hours old, the app requires the operator to use **Refresh stock first**; stock can also be refreshed on demand even while the cache is still valid.

Every printable label list has two destinations. **Print labels** uses the normal 50 × 30 mm SATO. **Print large labels** uses the Zebra ZD421 and its permanent 100 × 175 mm stock. The large path checks the Zebra only when requested and always shows a size, quantity, printer-status, and cost warning before its separate confirmation button becomes available. Zebra discovery uses its own MAC/IP cache, so it cannot replace the SATO's remembered address.

Successful assignment commits renew the barcode-administration session, including after a long large-batch write. The assigned item codes are also retained in browser session storage until stock labels are prepared or the operator chooses **Done**. If authentication still expires, the completion dialog accepts the PIN again and automatically resumes the MAIN stock lookup without losing that batch.

The service also exposes a narrow staff-label endpoint for PRV Pick & Pack. It uses the same SATO discovery, retry, spool and 50 × 30 mm Code 128 layout while accepting a staff name and generated `PPU-XXXX-XXXX` badge code.

MYOB supplies the PO item codes and ordered quantities. Descriptions are read from `sf_prodoptions` in the PRV syncer PostgreSQL database, with MYOB's stock-item description as a fallback. Barcodes are always read live from the MYOB `StockItem` `CrossReferences` collection, using the entry whose `AlternateType` is `Barcode`.

## Safety and network behavior

- `PRINT_ENABLED=false` is the default. Jobs are written to `spool/` but not transmitted.
- `BARCODE_ASSIGNMENT_ENABLED=false` is the default. Barcode previews work, but MYOB writes remain blocked until the setting is explicitly enabled.
- The unprotected **Enter barcodes** tab can write only when `BARCODE_ASSIGNMENT_ENABLED=true`. As requested it has no PIN prompt, so access to the web app must remain restricted to trusted warehouse staff.
- The SATO is identified by `PRINTER_MAC`, not its DHCP address.
- The last working address is cached under `data/` and checked before another LAN scan.
- A print retries discovery and connection up to three times only while zero payload bytes have been accepted. Once transmission starts, the job is never automatically repeated because raw port 9100 cannot retract already accepted labels.
- `PRINTER_CONNECT_TIMEOUT_SECONDS` keeps wake/discovery failures quick. `PRINTER_SEND_TIMEOUT_SECONDS` defaults to 180 seconds so a large batch can feed into the CG4's receive buffer while it is printing.
- A non-dismissible progress dialog freezes the label UI during transmission, explains that large batches can take several minutes, and warns if the page is closed or reloaded mid-job.
- Successful and delivery-uncertain jobs clear the printed selection in the browser to protect against accidental duplicate batches. A safe failure before any bytes were sent keeps the selection available for retry.
- Connections pause for `PRINTER_REOPEN_DELAY_MS` before reopening port 9100, as required by the CG4 LAN interface.
- Printing uses raw SBPL over TCP port 9100. CUPS is not required.
- Raw port 9100 confirms only that bytes were submitted; it does not provide a durable printer job ID or reliable print-complete acknowledgement. If a connection fails after partial transmission, the spool audit records the byte count and the UI tells staff to count the physical output rather than reprint the batch.
- The UI does not implement user authentication. Keep port 4050 restricted to the trusted warehouse LAN or place it behind the existing authenticated reverse proxy.

## Ubuntu deployment

```bash
git clone https://github.com/statichum/barcode-label-printer.git
cd barcode-label-printer
cp .env.example .env
nano .env
chmod 600 .env
mkdir -p data spool
docker compose pull
docker compose up -d
docker compose logs -f
```

For local diagnostics, the app remains available at `http://10.10.1.14:4050`. Staff tablets should use `https://labelstation.prv.co.nz` once the shared Caddy configuration below is deployed.

The container uses host networking because ARP discovery cannot cross a normal Docker bridge. It receives `NET_RAW`, not full privileged access. With host networking, the existing syncer PostgreSQL port is reached at `127.0.0.1:5432`.

## LAN HTTPS and PWA installation

The app includes a manifest, tablet icons and service worker. The service worker activates only in a secure browser context, so staff should install the app from `https://labelstation.prv.co.nz`, not the raw port 4050 address.

Only one Caddy container can bind the server's `10.10.1.14:443`. The existing PRV Pick & Pack Caddy is therefore the shared HTTPS gateway for both apps; do not start a second Caddy stack here. Its Caddyfile contains a second site block that sends `labelstation.prv.co.nz` to host port 4050.

Cloudflare needs a DNS-only (grey-cloud) `A` record for `labelstation.prv.co.nz` pointing to the server's reserved LAN address. The existing restricted Caddy token also needs `Zone / Zone / Read` and `Zone / DNS / Edit` for `prv.co.nz`; no new token, tunnel, proxy, or public router forwarding is required.

After updating this app, reload the shared gateway from the Pick & Pack directory:

```bash
cd /docker/PRV-PickPack
git pull --ff-only
docker compose up -d --build caddy
docker compose logs --tail=100 caddy

getent ahostsv4 labelstation.prv.co.nz
curl -fsS https://labelstation.prv.co.nz/api/health
```

The DNS command should show `10.10.1.14`, and the HTTPS health check must work without `-k`. On Android, open the HTTPS address in Chrome and choose **Install app**. On iPad, open it in Safari and choose **Share → Add to Home Screen**.

## Required `.env` values

Set these values in the server's untracked `.env`:

```dotenv
MYOB_USERNAME=PRVSyncerAPI
MYOB_PASSWORD=...
MYOB_COMPANY=PRV
DATABASE_PASSWORD=...

PRINTER_NAME=sato-barcode
PRINTER_MODEL=CG412DT-LAN
PRINTER_LANGUAGE=SBPL
PRINTER_MAC=00:19:98:84:26:F9
PRINTER_PORT=9100
ARP_INTERFACE=enp5s0
PRINTER_SEND_ATTEMPTS=3
PRINTER_RETRY_DELAY_MS=1000
PRINTER_PRINT_SPEED=2
PRINTER_DARKNESS=4A

LABEL_WIDTH_MM=50
LABEL_HEIGHT_MM=30
PRINTER_DOTS_PER_MM=12
PRINT_ENABLED=false

LARGE_PRINTER_NAME=zebra-large-label
LARGE_PRINTER_MODEL=ZD421
LARGE_PRINTER_LANGUAGE=ZPL
LARGE_PRINTER_MAC=60:95:32:06:E0:CF
LARGE_PRINTER_PORT=9100
LARGE_PRINTER_PRINT_SPEED=2
LARGE_PRINTER_DARKNESS=20
LARGE_LABEL_WIDTH_MM=100
LARGE_LABEL_HEIGHT_MM=175
LARGE_PRINTER_DOTS_PER_MM=8
LARGE_PRINT_ENABLED=false

BARCODE_ADMIN_PIN=choose-a-4-to-12-digit-pin
BARCODE_ADMIN_SESSION_MINUTES=30
BARCODE_ASSIGNMENT_ENABLED=false
```

For the CG4, print speed `2`, `3`, and `4` select 50, 75, and 100 mm/s respectively. Darkness accepts `1A` through `5A`. Start at speed `2` and darkness `4A`, then reduce darkness if barcode bars become thick or lose edge definition.

The supplied MYOB endpoint currently needs certificate verification disabled, matching the successful `curl -k` test:

```dotenv
MYOB_VERIFY_SSL=false
```

Re-enable verification when the endpoint presents a certificate trusted by the container.

## Barcode assignment safeguards

The generated value follows PRV's spreadsheet rule: `04`, a zero-padded ten-digit sequence, and the EAN-13 check digit. The first assignment preview after this upgrade performs a one-time scan of **all** MYOB stock items, including inactive items, to seed the highest existing PRV sequence. This can take several minutes. Later previews do not repeat that full scan.

Before each preview is shown, the app takes a filesystem lock, permanently reserves the complete sequence range, writes the new high-water mark to `data/barcode-sequence.json`, flushes it to the persistent Docker volume, and then releases the lock. Concurrent operators therefore receive disjoint ranges. Closing or abandoning a preview leaves an intentional gap; reserved numbers are never returned to the pool. If the counter file is invalid or unreadable, barcode assignment fails closed instead of rebuilding or risking reuse. Keep the `data/` directory persistent and include it in server backups; do not delete or edit `barcode-sequence.json`.

The stored active-item catalogue is checked for collisions against Barcode rows only. Global, vendor, customer, and other cross-reference types are deliberately ignored because MYOB permits the same value to also be stored as a Barcode. Normal catalogue refreshes remain active-only.

Immediately before writing, the app reads the selected items from MYOB, repeats the collision check, and uses the current-session Barcode detail row IDs. Items with multiple Barcode rows are refused and must be cleaned up in MYOB first. An existing row is deleted and its replacement is created in the same StockItem PUT—the behavior verified against the PRV endpoint. After writing, the assigned items are read back from MYOB and verified. **Select all filtered** includes matching items beyond the first 250 displayed rows. The normal limit is 350 assignments; an administrator can re-enter the PIN to unlock the full filtered catalogue for only that administration session. The server enforces the unlock, and it expires with the session.

Enable writes when ready to use the assignment screen:

```dotenv
BARCODE_ASSIGNMENT_ENABLED=true
```

Restart the service after changing the setting.

## First label test

1. Keep `PRINT_ENABLED=false`.
2. Look up PO `000796` or add one known item manually.
3. Create a test job from the UI.
4. Confirm a `.sbpl` file and matching `.json` audit record appear in `spool/`.
5. Set `PRINT_ENABLED=true` and restart:

```bash
docker compose up -d
docker compose logs -f
```

6. Print one label, check orientation, margins, gap sensing, barcode scanning, and text fit before printing a full PO.

For the first large-label test, leave `LARGE_PRINT_ENABLED=false`, create one large test job, and inspect the `.zpl` file plus its `.json` audit record. Then set `LARGE_PRINT_ENABLED=true`, restart, and print exactly one 100 × 175 mm label. Check orientation, top-of-form calibration, description wrapping, barcode scanning and item-code reading distance before increasing the quantity.

## Local build

```bash
docker compose -f compose.yaml -f compose.local.yaml up -d --build
curl -s http://127.0.0.1:4050/api/health
curl -s http://127.0.0.1:4050/api/printer/status
```

PRV Pick & Pack submits staff badges server-to-server with:

```http
POST /api/staff-labels/print
Content-Type: application/json

{"name":"Chris Tuckey","badge_code":"PPU-7K4M-92QX","quantity":1}
```

The staff endpoint does not query MYOB or PostgreSQL. With `PRINT_ENABLED=false` it creates normal `.sbpl` and `.json` spool files; with printing enabled it sends the job through the existing SATO printer connection.

## Updating

```bash
git pull
docker compose pull
docker compose up -d
docker compose logs -f
```

Every push to `main` runs linting and tests, then publishes `ghcr.io/statichum/barcode-label-printer:latest`.
