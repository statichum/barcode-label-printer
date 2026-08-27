from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_home_page_declares_web_app_icons():
    response = client.get("/")

    assert response.status_code == 200
    assert 'rel="manifest" href="/static/manifest.webmanifest"' in response.text
    assert 'rel="apple-touch-icon"' in response.text
    assert 'name="apple-mobile-web-app-capable" content="yes"' in response.text
    assert 'id="stock-label-reauth"' in response.text
    assert 'id="entry-tab"' in response.text
    assert 'id="barcode-entry-form"' in response.text
    assert "Manage barcodes." in response.text
    assert "Print labels, enter supplier barcodes, or assign new ones." in response.text
    assert "Print product labels." not in response.text


def test_web_app_manifest_and_icons_are_served():
    manifest = client.get("/static/manifest.webmanifest")

    assert manifest.status_code == 200
    assert manifest.json()["name"] == "PRV Label Station"
    assert manifest.json()["display"] == "standalone"
    assert len(manifest.json()["icons"]) == 3

    icon = client.get("/static/icon-192.png")
    assert icon.status_code == 200
    assert icon.headers["content-type"] == "image/png"
    assert icon.content.startswith(b"\x89PNG\r\n\x1a\n")

    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"] == "image/png"


def test_label_ui_defaults_to_natural_sort_and_clears_a_successful_batch():
    page = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'data-sort="natural" class="active"' in page
    assert 'sortMode: "natural"' in script
    assert 'state.sortMode = "natural";' in script
    assert "state.items.forEach((item) => { item.selected = false; });\n    rerenderCurrentResults();" in script


def test_barcode_entry_ui_uses_unprotected_catalogue_and_batch_commit_endpoints():
    page = client.get("/").text
    script = client.get("/static/app.js").text

    assert "Print from PO" in page
    assert "Manual Print" in page
    assert 'id="refresh-barcode-entry-stock"' in page
    assert 'id="refresh-and-prepare-stock-labels"' in page
    assert "On hand" in page
    assert 'api(`/api/barcode-entry/items${refresh ? "?refresh=true" : ""}`)' in script
    assert 'api("/api/barcode-entry/commit"' in script
    assert 'api("/api/barcode-entry/stock-on-hand/refresh"' in script
    assert '"?refresh_stock=true"' in script
    assert "terms.every((term) => searchable.includes(term))" in script
    assert 'barcode !== "x"' in script
    assert "const catalogueRenderBatchSize = 250;" in script
    assert 'button.textContent = `Load ${nextCount.toLocaleString("en-NZ")} more`;' in script
    assert script.count('addEventListener("scroll"') >= 2
