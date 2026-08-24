# PRV Barcode Label Printer

A small internal web service for preparing and printing 50 × 30 mm product labels on the networked SATO CG412DT-LAN.

The operator can:

- enter a MYOB Advanced purchase-order number;
- review the order's inventory lines, selected by default;
- exclude lines or change label quantities;
- add item codes and quantities manually; and
- print the item description, item code, and scannable Code 128 barcode.

MYOB supplies the PO item codes and ordered quantities. The description and barcode are read from `sf_prodoptions` in the PRV syncer PostgreSQL database.

## Safety and network behavior

- `PRINT_ENABLED=false` is the default. Jobs are written to `spool/` but not transmitted.
- The SATO is identified by `PRINTER_MAC`, not its DHCP address.
- The last working address is cached under `data/` and checked before another LAN scan.
- If sending fails, the cache is invalidated, the printer is rediscovered, and the job is retried once.
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

LABEL_WIDTH_MM=50
LABEL_HEIGHT_MM=30
PRINTER_DOTS_PER_MM=12
PRINT_ENABLED=false
```

The supplied MYOB endpoint currently needs certificate verification disabled, matching the successful `curl -k` test:

```dotenv
MYOB_VERIFY_SSL=false
```

Re-enable verification when the endpoint presents a certificate trusted by the container.

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

## Updating

```bash
git pull
docker compose pull
docker compose up -d
docker compose logs -f
```

Every push to `main` runs linting and tests, then publishes `ghcr.io/statichum/barcode-label-printer:latest`.
