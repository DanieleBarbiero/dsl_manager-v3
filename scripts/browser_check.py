"""Browser acceptance and screenshots. Run against a new local workspace."""

import json
import sys
import subprocess
import time
import urllib.request
import atexit
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base = "http://127.0.0.1:8766"
workspace = sys.argv[1] if len(sys.argv) > 1 else "runtime/browser_verified"
server = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "dslm3",
        "--workspace",
        workspace,
        "serve",
        "--no-browser",
        "--port",
        "8766",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
atexit.register(server.terminate)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for _ in range(100):
    try:
        opener.open(base, timeout=1).close()
        break
    except OSError:
        time.sleep(0.1)
else:
    raise RuntimeError("Local test server did not start")
reports = Path(__file__).resolve().parents[1] / "reports"
reports.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page(
        viewport={"width": 1440, "height": 1080}, device_scale_factor=1
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base)
    expect(page.locator("h1")).to_have_text("Panoramica")
    expect(page.get_by_role("button", name="Carica il laboratorio")).to_be_visible()
    expect(page.locator("#workspace-select")).to_be_visible()
    expect(page.get_by_text("Il passaggio 02 è il gate ricorrente.")).to_be_visible()

    def wait_job(count):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            jobs = page.request.get(base + "/api/jobs").json()
            if len(jobs) > count and jobs[-1]["status"] not in ["queued", "running"]:
                return jobs[-1]
            page.wait_for_timeout(200)
        raise AssertionError("Browser job timed out")

    def run(button):
        count = page.evaluate("fetch('/api/jobs').then(r=>r.json()).then(x=>x.length)")
        button.click()
        job = wait_job(count)
        assert job["status"] == "success", job
        expect(page.locator("#job-banner")).to_be_hidden(timeout=10000)

    run(page.get_by_role("button", name="Carica il laboratorio"))
    page.locator("nav a[data-page=settings]").click()
    run(page.get_by_role("button", name="Profilo conservativo", exact=True))
    page.locator("nav a[data-page=overview]").click()
    run(page.get_by_role("button", name="Pipeline rapida"))
    page.screenshot(path=reports / "ui_overview.png", full_page=True)
    visited = []
    for name in [
        "sources",
        "review",
        "ai",
        "temporal",
        "knowledge",
        "exports",
        "settings",
    ]:
        page.locator(f"nav a[data-page={name}]").click()
        expect(page.locator("h1")).to_be_visible()
        assert page.evaluate(
            "document.documentElement.scrollWidth<=window.innerWidth"
        ), name
        visited.append(name)
    page.locator("nav a[data-page=sources]").click()
    page.get_by_role("button", name="Esplora").first.click()
    expect(page.locator("#detail")).to_be_visible()
    page.locator("#close-detail").click()
    page.locator("nav a[data-page=ai]").click()
    run(page.get_by_role("button", name="Prepara entrambe le route"))
    packages = page.evaluate("fetch('/api/packages').then(r=>r.json())")
    package = next(x for x in packages if x["route"] == "domain_interpretation")
    evidence = page.evaluate("fetch('/api/evidence').then(r=>r.json())")
    e = next(
        e for e in evidence if e["kind"] == "chunk" and e["path"].endswith(".docx")
    )
    payload = {
        "record_type": "candidate_fact",
        "candidate_id": "browser_001",
        "source_revision_id": e["revision_id"],
        "evidence_id": e["id"],
        "evidence_text": "Una richiesta P1 deve essere presa in carico entro 30 minuti.",
        "assertion_type": "inferred",
        "confidence": "medium",
        "fact_type": "domain",
        "entity_name": "Priorità P1",
        "property_name": "presa_in_carico_minuti",
        "property_value": 30,
    }
    before = page.evaluate("fetch('/api/jobs').then(r=>r.json()).then(x=>x.length)")
    page.locator(f'.ai-response[data-id="{package["id"]}"]').set_input_files(
        {
            "name": "risposta_browser.jsonl",
            "mimeType": "application/json",
            "buffer": (json.dumps(payload) + "\n").encode(),
        }
    )
    assert wait_job(before)["status"] == "success"
    expect(page.locator("#job-banner")).to_be_hidden(timeout=10000)
    page.locator("nav a[data-page=review]").click()
    expect(page.locator(".candidate-check")).to_have_count(1)
    page.locator(".candidate-check").check()
    run(page.get_by_role("button", name="Conferma selezionate"))
    run(page.get_by_role("button", name="Merge delle confermate"))
    page.locator("#review-filter").select_option("confirmed")
    page.screenshot(path=reports / "ui_review.png", full_page=False)
    page.get_by_role("button", name="Valuta", exact=True).first.click()
    expect(page.locator("#detail")).to_be_visible()
    page.screenshot(path=reports / "ui_review_detail.png")
    page.locator("#close-detail").click()
    page.locator("nav a[data-page=exports]").click()
    run(page.get_by_role("button", name="Crea snapshot", exact=True))
    with page.expect_download() as download:
        page.get_by_role("link", name="JSON", exact=True).first.click()
    assert download.value.suggested_filename == "dsl.json"
    run(page.get_by_role("button", name="Dinamico", exact=True).first)
    expect(page.locator("#detail")).to_be_visible()
    page.locator("#close-detail").click()
    page.locator("nav a[data-page=knowledge]").click()
    page.screenshot(path=reports / "ui_knowledge.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("nav a[data-page=overview]").click()
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
    expect(page.locator("h1")).to_have_text("Panoramica")
    page.evaluate("scrollTo(0,0)")
    page.wait_for_timeout(200)
    page.screenshot(path=reports / "ui_mobile.png", full_page=False)
    assert page.evaluate("document.documentElement.scrollHeight") < 3000
    assert not errors, errors
    (reports / "browser_result.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "pages": visited,
                "js_errors": errors,
                "flow": "Vega -> pipeline rapida -> AI JSONL -> review/merge -> snapshot/download/GEXF; navigazione esplicita 00-06 e selettore workspace verificati",
                "viewports": ["1440x1080", "390x844"],
            },
            indent=2,
        )
    )
    browser.close()
    server.terminate()
    server.wait(timeout=10)
