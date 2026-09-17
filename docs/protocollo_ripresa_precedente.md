DSLM3 — diario integrativo e protocollo di ripresa


STATO: IMPLEMENTAZIONE AVANZATA, CONSEGNA FINALE NON CHIUSA


La riscrittura è stata implementata ed eseguita nell'ambiente locale. L'ambiente si è poi disconnesso: exec_command e gli upload dei file locali restituiscono “409 Conflict, environment_offline: Environment is not connected”. I retry non hanno ripristinato l'accesso. Non è un'assenza di accesso al web: Google Drive continua a funzionare. Questa nota è salvata direttamente come documento nativo per conservare lo stato operativo.


SALVATAGGIO E VINCOLI


Directory autorizzata: gdrive/projects/dslm3, ID 1r2VoHKdml3Nfk2AogSLXiGbNqydY-rQT.
Checkpoint persistente già verificato: dslm3_checkpoint.zip, file ID 1N4BDmNGwOvJL2fyGidEzlcRFe6EwflRH, 1.161.273 byte. Comprende codice, test, documentazione e report del momento in cui è stato salvato. NON contiene necessariamente le ultime modifiche descritte sotto.
Documenti Markdown persistenti: obiettivi.md, diario_tecnico.md, matrice_parita.md.
Nessuna scrittura, commit, push, issue o PR su GitHub. Repository v1 letto al commit c443b6a457b78229517a481fc5850dc8b44ecc3a.


PERCORSI DA RECUPERARE


Workspace di esecuzione: /workspace/scratch/f8392732e1af
Progetto corrente: /workspace/scratch/f8392732e1af/dslm3
Ambiente virtuale: /workspace/scratch/f8392732e1af/.venv
Baseline: /workspace/scratch/f8392732e1af/reference/dsl_manager-v1
Allegato originale: /workspace/scratch/f8392732e1af/upload/dslm1+vega.md
Mappa dei salvataggi: /workspace/scratch/f8392732e1af/drive_sync_state.json
I file locali potrebbero essere recuperabili dopo la riconnessione; non è stato possibile verificare la loro disponibilità dopo l'interruzione.


VERIFICHE CONCLUSE REALMENTE


1. Ultima suite completa conclusa: 70 test passati, 2 warning di deprecazione delle dipendenze FastAPI/Starlette, 31,91 secondi. Log locale reports/full_acceptance_tests.log.
2. Vega M3: 19/19 controlli passati in una precedente esecuzione pulita. Sei fonti reali, conversioni Docling reali, 52 evidenze, 30 fatti, 24 relazioni, un conflitto reale P1 e un intervallo. Questi conteggi si riferiscono a quella versione; modifiche successive del parser richiedono un nuovo laboratorio.
3. Browser Chromium reale: percorso Vega → pipeline → package delle due route → risposta JSONL → review → merge → snapshot → download → GEXF passato, nessun errore JavaScript, viewport desktop e mobile. Questa esecuzione precede le ultime modifiche.
4. PDF reale Docling: conversione riuscita con modelli OCR/layout/tabelle realmente scaricati; testo atteso rilevato. DOCX e XLSX reali convertiti.
5. Formati aggiuntivi verificati attraverso il worker reale: CSV, TSV, JSON, JSONL, YAML con data, EML, MHTML, XLS, ODS con formula, PPTX, HTML, SQL UTF-16.
6. Excel: golden strutturale v1 coincidente, formula/cache distinte, fogli hidden/very_hidden, link non dereferenziati, macro non eseguita e hash verificato.
7. Governance: pending esclusi dal merge, batch atomici, citazioni false rifiutate, correzioni append-only, revoche, supporti multipli, strict merge, staleness, riavvio e idempotenza.
8. SQL: regressioni dei falsi riferimenti del rapporto, package e separatori, CTE, sinonimi/link/viste materializzate, blocchi anonimi, variabili INTO non promosse a tabelle, subquery di funzioni PostgreSQL, procedure T-SQL.
9. Temporalità: anno/mese/giorno, DST e timezone, precisione minuto/millisecondo/microsecondo, istanti equivalenti con offset differenti, correlazione di copie, propagazione disgiunta e HTML/JSON-LD.
10. GEXF: test di nodi fatti/fonti/conflitti, attributi/provenienza, spells e XSD offline conclusi nella suite dei 70 test.


IMPLEMENTAZIONE E CORREZIONI SUCCESSIVE AL CHECKPOINT


Il progetto usa un servizio applicativo comune UI/CLI, SQLite transazionale con ledger append-only e viste effettive, un solo worker parser isolato, frontend HTML/CSS/JS senza build Node.
Docling 2.128.0, SQLGlot 30.18.0, FastAPI 0.141.1. Correzione SIGBUS: OpenCV 4.12.0.88 con NumPy 2.2.6 e PyTorch CPU. Playwright 1.56.0/Chromium headless installato dopo fallimenti della distribuzione più recente.
Migrazione SQLite 2: un candidato tecnico è effettivo soltanto se la sua evidenza appartiene all'interpretazione corrente. Ritornare a un dialetto già usato riattiva la cache tramite un nuovo record append-only.
Deduplicazione delle evidenze identiche e tabella parse_evidence per retry idempotenti.
YAML: timestamp mantenuti come stringhe; ODS: superamento budget rifiutato, senza troncamento silenzioso.
SQL: separatori client delimitano realmente le unità, blocchi anonimi riconosciuti; SELECT INTO su variabili locali non crea dipendenze a tabelle inesistenti; parentesi esterne alla subquery non rompono il suo AST.
Temporalità: precisione fine preservata, concordanza degli istanti normalizzata per confronto, dichiarazioni con underscore Markdown riconosciute. Il package AI non può introdurre direttamente intervalli temporali; il flusso temporale deve essere esplicito.
GEXF: aggiunti nodi di fatti, fonti e conflitti, archi mentions/derives_from/conflicts_with, attributi e citazioni; opzioni include_sources/include_fact_nodes/include_conflicts esposte dal dispatch.
Il frontend conserva visibile il messaggio di errore quando una review/correzione fallisce.


ULTIME MODIFICHE ANCORA DA RIVERIFICARE


Dopo la suite dei 70 test:
- Identità delle proposte deterministiche resa indipendente dall'intero batch/corpus per non riaprire review invariate quando si aggiunge una fonte; aggiunto test incrementale.
- Propagazione dello stato partial fino al run/pipeline e alla CLI; aggiunto test.
- Validazione del tipo dei percorsi upload.
- Dipendenze principali fissate; aggiunti esplicitamente psutil, tzdata per Windows, BeautifulSoup; aggiornato extra dev.
- Formattazione Python con Ruff e JavaScript con jsbeautifier; rimosse quattro assegnazioni inutilizzate e due generatori fixture legacy non applicabili.
- Scritti README.md, Install.cmd, Avvia.cmd, install.sh e avvia.sh.
- Non è stata conclusa una nuova suite completa su quest'ultimo stato. Non dichiarare 72 test passati prima di eseguirli.


PASSAGGI RIMANENTI — STEP 08 APERTO


A. Ripristinare l'accesso all'ambiente. Recuperare i file correnti; se non disponibili, ripartire dallo ZIP persistente applicando le modifiche documentate e il contesto della conversazione.
B. Eseguire subito un checkpoint aggiornato su Drive prima di altre modifiche.
C. Completare manuale_operativo.md, architettura.md, formati_e_limiti.md, THIRD_PARTY_NOTICES.md, rapporto finale e diario. I tentativi di scrivere manuale/architettura si sono fermati prima dell'applicazione della patch.
D. Aggiungere le istruzioni riproducibili del controllo PDF, registrare le versioni effettive in requirements-tested-linux.txt e completare il manifest di rilascio.
E. Eseguire lint finale e pytest completo. Risolvere errori reali, senza aggiustare i test per nasconderli. Ripetere Vega e browser in workspace nuovi perché il parser e GEXF sono cambiati.
F. Verificare gli screenshot finali desktop/mobile e review, senza basarsi soltanto sull'assenza di errori JS.
G. Costruire wheel, verificarne risorse statiche, fixture Vega e XSD; fare smoke test dal wheel fuori dai sorgenti. Windows non è stato eseguito in questa sessione: non dichiararlo testato.
H. Creare archivio finale con codice, test, fixture, documenti e report; escludere ambiente virtuale, cache, runtime, credenziali e residui di build. Salvare tutto in gdrive/projects/dslm3 e verificare i salvataggi.
I. Chiudere lo step 08 soltanto dopo queste prove. Fornire link e istruzioni di avvio. Nessuna scrittura GitHub.


LIMITI DA MANTENERE ESPLICITI


Il catalogo SQLGlot contiene 33 dialetti nominati più generic; non tutti sono stati collaudati con un corpus completo. Dieci dialetti hanno casi DDL dedicati, ulteriori casi procedurali riguardano Oracle/PostgreSQL/T-SQL/MySQL. DB2, Firebird, Informix e Sybase sono lexical-only. Una versione non può sempre essere inferita dalla sintassi condivisa.
Il parser non esegue SQL e non è un compilatore procedurale completo. SQL dinamico resta irrisolto. ALTER/DROP sono riconosciuti come operazioni, senza simulare l'intero catalogo risultante di uno storico di migrazioni.
XLS/XLSB non garantiscono la stessa struttura/formula/cache di OOXML; XLSB non risulta ancora collaudato con fixture reale. Altri formati Docling dichiarati ma non testati vanno distinti da quelli effettivamente verificati.
Gli ID e i dettagli dello schema M3 sono nuovi. Nessuna migrazione automatica dei registri/review v1; si reimporta il corpus e si conserva l'archivio v1.
La propagazione temporale è esplicita e una tantum: non è inferenza continua che si ricalcola dopo ogni revoca della premessa.
Le risposte AI del laboratorio sono fixture dichiarate; nessun modello esterno è stato chiamato.
Non promettere assenza universale di bug o “tutti i dialetti e tutte le versioni”.