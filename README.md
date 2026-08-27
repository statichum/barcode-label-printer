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

The **Enter barcodes** tab shares the stored active-stock catalogue and manual MYOB refresh used by **Assign barcodes**, but does not require the administration PIN. Search or filter the list, tap an item, scan its existing manufacturer barcode, and add it to a batch before choosing **Send to MYOB**. Real barcode values are never silently overwritten; missing rows are created and `x` placeholders are replaced. Each batch is checked for duplicate barcode values, re-reads its selected items immediately before writing, and reads them back afterward to verify MYOB stored the expected values. A partial failure leaves the browser batch intact so it can be refreshed and safely retried.

The **Assign barcodes** tab is protected by a server-configured PIN. It loads active MYOB stock items for local code/description searching, shows each current Barcode cross-reference, previews generated internal EAN-13 values, rechecks the stored active-item snapshot for collisions, and then updates MYOB. The snapshot is stored in `data/barcode-stock-items.json`, survives container restarts, and changes only after a manual refresh or successful assignment. Concurrent refresh requests share one MYOB catalogue load. Review uses this local snapshot rather than downloading the catalogue again. Barcode numbers are allocated separately by a persistent, atomically locked high-water counter in `data/barcode-sequence.json`. Immediately before writing, confirmation reads only the selected items from MYOB so current Barcode row IDs are used; those items are read back again after writing for verification. An existing Barcode detail row—including an `x` placeholder—is deleted by its MYOB detail `id` and replaced in the same PUT; a new row is appended only when no Barcode row exists.

After a successful assignment, the operator can prepare labels for those items using current `QtyAvailable` in the `MAIN` warehouse. The availability result is loaded only when requested, filtered to the newly assigned items, and opened in the normal label review list before printing.

Successful assignment commits renew the barcode-administration session, including after a long large-batch write. The assigned item codes are also retained in browser session storage until stock labels are prepared or the operator chooses **Done**. If authentication still expires, the completion dialog accepts the PIN again and automatically resumes the MAIN stock lookup without losing that batch.

The service also exposes a narrow staff-label endpoint for PRV Pick & Pack. It uses the same SATO discovery, retry, spool and 50 × 30 mm Code 128 layout while accepting a staff name and generated `PPU-XXXX-XXXX` badge code.

MYOB supplies the PO item codes and ordered quantities. Descriptions are read from `sf_prodoptions` in the PRV syncer PostgreSQL database, with MYOB's stock-item description as a fallback. Barcodes are always read live from the MYOB `StockItem` `CrossReferences` collection, using the entry whose `AlternateType` is `Barcode`.

## Safety and network behavior

- `PRINT_ENABLED=false` is the default. Jobs are written to `spool/` but not transmitted.
- `BARCODE_ASSIGNMENT_ENABLED=false` is the default. Barcode previews work, but MYOB writes remain blocked until the setting is explicitly enabled.
- The unprotected **Enter barcodes** tab can write only when `BARCODE_ASSIGNMENT_ENABLED=true`. As requested it has no PIN prompt, so access to the web app must remain restricted to trusted warehouse staff.
- The SATO is identified by `PRINTER_MAC`, not its DHCP address.
- The last working address is cached under `data/` and checked before another LAN scan.
- A print uses three complete discovery/connect/send attempts by default. Failed attempts force fresh MAC discovery so a sleeping printer or temporarily closed port can recover.
- Successful jobs clear the printed selection in the browser to protect against accidental duplicate batches; failed jobs keep it selected for retry.
- Connections pause for `PRINTER_REOPEN_DELAY_MS` before reopening port 9100, as required by the CG4 LAN interface.
- Printing uses raw SBPL over TCP port 9100. CUPS is not required.
- Raw port 9100 confirms that bytes were submitted, but does not provide a durable printer job ID.
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

Open `http://10.10.1.14:4050` from the warehouse network.

The container uses host networking because ARP discovery cannot cross a normal Docker bridge. It receives `NET_RAW`, not full privileged access. With host networking, the existing syncer PostgreSQL port is reached at `127.0.0.1:5432`.

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

The stored active-item catalogue is still checked for alternate-ID collisions, covering Barcode, Global, vendor, and customer references already present in that snapshot. Normal catalogue refreshes remain active-only.

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
