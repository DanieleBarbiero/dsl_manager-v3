# DSLM3 3.0.0 — rapporto di consegna

Data: 17 settembre 2026. **Rilascio 3.0.0 concluso e consegnato.**

## Risultato

La riscrittura è un'applicazione eseguibile con UI web locale, servizio comune UI/CLI, persistenza SQLite, parser reali, governance delle proposte, temporalità, round-trip AI ed export. Il flusso viene provato fino al DSL e al grafo; le conversioni Docling non sono simulate.

Baseline: `dsl_manager-v1`, commit `c443b6a457b78229517a481fc5850dc8b44ecc3a`. La riscrittura contiene 21 moduli Python applicativi, circa 7.900 righe incluse le parti OOXML riutilizzate, contro 77 moduli / 40.092 righe inventariati nella v1. Il riutilizzo è dichiarato in `THIRD_PARTY_NOTICES.md`.

## Prove della versione consegnata

| Verifica | Esito | Evidenza |
|---|---|---|
| Suite completa | **79 passed**, 2 warning di deprecazione nelle dipendenze di test | `reports/acceptance_tests_final.log` |
| Vega M3, workspace nuovo | **19/19 controlli passati** | `reports/vega_release_final.json` |
| UI Chromium reale | Percorso completo, download, zero errori JavaScript; desktop e mobile | `reports/browser_result.json`, screenshot `ui_*.png` |
| PDF Docling reale | SUCCESS, testo atteso e dichiarazione temporale riconosciuti | `reports/pdf_result_final.json` |
| Installazione wheel fuori dai sorgenti | Sei fonti, pipeline, risorse UI/Vega/XSD e GEXF verificati | `reports/wheel_result.json` |
| Dipendenze | `pip check` senza incompatibilità | `reports/dependency_check.log` |
| Controllo statico | Ruff, regole F: nessun errore | `reports/lint.log` |
| Salvataggio Drive | 141/141 file di contenuto riletti nei metadata; corrispondenza nome/dimensione e hash locali di upload | `reports/drive_verification.json`, `release_manifest.json` |
| Integrità e ripartenza | SQLite, cache, riavvio e merge idempotenti | Suite e laboratorio Vega |

L'ambiente eseguito usa Python 3.12.14, Docling 2.128.0, SQLGlot 30.18.0, FastAPI 0.141.1, PyTorch 2.14.0 CPU, NumPy 2.2.6 e OpenCV 4.12.0.88. `requirements-tested-linux.txt` registra le versioni complete; è una fotografia Linux, non un lock universale Windows.

## Risultato Vega

Sei fonti processate con successo producono **52 evidenze**. Dopo il round-trip AI controllato e la review: **30 fatti, 24 relazioni, 32 entità, un conflitto reale P1 e un intervallo temporale**.

Sono verificate le due tabelle e le nove colonne del DDL, i quattro campi Forms e la chiamata alla procedura, l'assenza delle false colonne segnalate nel rapporto v1, le cinque occorrenze log senza falsi conflitti, il workbook strutturale e il testo Docling. Le risposte AI sono fixture dichiarate: il conflitto 30 minuti / 1 ora deriva dalle citazioni di manuale e matrice, non da una chiamata a un modello esterno.

## Correzioni completate nella ripresa

- Recupero dal checkpoint precedente e ricostruzione delle modifiche descritte ma non salvate.
- Supporti limitati all'interpretazione corrente; cache riattivabile con ledger append-only.
- Identità deterministiche stabili quando si aggiungono fonti, senza riaprire review invariate; appartenenza corretta ai batch.
- Separazione delle unità SQL con terminatori client, blocchi anonimi, variabili INTO e subquery procedurali.
- Preservazione di timestamp YAML, rifiuto dei budget ODS senza troncamento, validazione dei percorsi upload.
- Precisione temporale, equivalenza degli offset e dichiarazioni Markdown, incluse quelle con underscore escapati da Docling.
- GEXF con fatti, fonti, conflitti e provenienza; controllo delle risorse XSD e intervalli.
- Propagazione dello stato partial fino alla UI/CLI e conservazione dei messaggi di errore di review.
- Documentazione, launcher Windows/Linux, pacchetto Python e verifiche riproducibili.

## Limiti della consegna

Windows dispone dei launcher ma **non è stato eseguito** in questa sessione. I 33 dialetti del backend SQL non equivalgono a 33 corpus completi collaudati: dieci hanno casi DDL dedicati; DB2/Firebird/Informix/Sybase restano lessicali. Non si promette riconoscimento certo di ogni versione, compilazione procedurale completa o risoluzione del SQL dinamico.

XLSB è integrato ma manca una fixture binaria reale di accettazione. Alcuni formati Docling hanno instradamento senza test dedicati. Non è prevista la migrazione automatica del registro di review v1. La propagazione temporale è esplicita una tantum. Per tutti i dettagli vedere `formati_e_limiti.md`.

Non rimangono errori nei test eseguiti. Questo non equivale a una garanzia universale di assenza di bug.

## Avvio e salvataggio

Su Windows: copiare la struttura del progetto, eseguire `installa.cmd`, poi `avvia.cmd`. Serve Python 3.12 a 64 bit. La UI si apre su `http://127.0.0.1:8765`.

Codice, test, fixture, manuali e report sono conservati come singoli file nella cartella `gdrive/projects/dslm3`. Nessun nuovo ZIP è usato per salvare il lavoro. Il vecchio checkpoint e il protocollo della disconnessione sono storici; `START_HERE.md` identifica lo stato corrente. Nessuna scrittura su GitHub.
