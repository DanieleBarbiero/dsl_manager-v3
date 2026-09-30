# Diario tecnico DSLM3

## 2026-09-17 — Bootstrap e analisi

- Identificato repository tramite plugin GitHub; acquisito clone locale in sola lettura. Commit: `c443b6a457b78229517a481fc5850dc8b44ecc3a`. Nessuna mutazione remota.
- Identificata cartella `gdrive/projects` e creata `dslm3` al suo interno.
- Letti AGENTS.md, pyproject, riepilogo, analisi tecnica, inventario dei moduli e rapporto allegato completo. `.wb` escluso come richiesto dalle istruzioni della baseline.
- Web e download PyPI/GitHub raggiungibili: controlli HTTP riusciti. Python runtime 3.12.14.
- Docling disponibile su PyPI: 2.128.0; baseline usa 2.97.0. Avviata installazione isolata in `.venv` esterna ai sorgenti distribuibili. Log integrale in `reports/environment_install.log`.
- Inventario: 40.092 righe Python, 77 moduli, 44 file di test; v1 contiene un motore di governance e temporalità significativamente più ampio del solo tutorial Vega.
- Requisiti acquisiti: workbook OOXML strutturale separato dalla vista Docling; candidati e review append-only; supporti effettivi; selezione AI tecnica/di dominio; temporalità e GEXF dinamico.
- Difetti da coprire obbligatoriamente con regressioni: falsi conflitti log; `<item>` Forms e attributo `operation`; falsa qualificazione SQL in subquery; round-trip AI senza merge (tutor v13 già affronta l'ordine, ma il nuovo flusso deve renderlo strutturalmente evidente).
- Decisione: implementazione nuova e compatta con un solo servizio applicativo per UI e CLI; riuso motivato consentito per algoritmi puri già robusti, in particolare preflight/manifest OOXML e risorse XSD offline. Nessun wrapper presentato come riscrittura.

Le voci successive registreranno comandi, verifiche e correzioni effettivamente eseguiti.

## Ambiente — primo controllo eseguibile

Installazione completa conclusa (Docling 2.128.0, SQLGlot 30.18.0, FastAPI 0.141.1). Lo smoke test di import/conversione termina con SIGBUS: il gate non è superato. Avviata diagnosi degli import nativi e sostituzione PyTorch con build CPU; nessuna conversione viene dichiarata riuscita.

## Ambiente — correzione e chiusura gate 01/02

- Diagnosi eseguibile: import di `torch`, NumPy, pydantic, lxml e pypdfium2 riuscito; `cv2` 5.0.0.93 terminava con SIGBUS. Fissato `opencv-python==4.12.0.88` con NumPy 2.2.6. PyTorch 2.14.0+cpu e torchvision 0.29.0+cpu installati per ridurre i requisiti GPU.
- `pip check`: nessuna dipendenza incompatibile. Eliminati solo i residui `~orch*` dell'uninstall pip nell'ambiente temporaneo.
- Conversioni Docling reali: `manuale_operativo_vega_2026.docx` SUCCESS, 796 caratteri; `matrice_priorita_vega_2026.xlsx` SUCCESS, 923 caratteri. Markdown in reports. Nessun mock usato.
- La matrice corrente ha intestazioni diverse da quelle narrate nell'allegato; le asserzioni del laboratorio useranno i byte attuali del commit baseline.
- Matrice di parità e scelte architetturali registrate. Gate 01/02 chiusi; inizia lo step 03.

## Step 03 — parser e acquisizione

- 18 test eseguiti e passati; copertura Oracle/Postgres/MySQL/T-SQL/SQLite/BigQuery/Snowflake/DuckDB/Spark/Teradata, ambiguità e marker legacy, citazioni XML e rifiuto entity, log separati, golden workbook, macro hash e budget.
- Primo test negativo ha scoperto che SQLGlot può accettare un'espressione isolata come SQL: aggiunto controllo del tipo AST radice; ripetizione suite riuscita.
- Primo batch reale: sei fonti Vega, sei successi, zero partial, zero errori, 51 evidenze; due conversioni Docling reali attraverso worker isolato. Report `vega_parse_first.json`.
- La matrice Excel corrente assegna P1=1 ora; il manuale P1=30 minuti. È una discordanza di dominio reale da mostrare nel laboratorio AI, distinta dai falsi conflitti degli eventi log.
- Schema delle tabelle e scope SQL impediscono le false colonne del rapporto. Un parser non riconosciuto conserva byte/diagnostica, senza derivazione automatica.
- Inizia step 04, governance e consolidamento.

## Step 04 e 05 — governance e temporalità

- Primo test governance ha individuato un errore nel numero di placeholder SQL della scrittura review; corretto e ripetuta la suite: 25 test passati.
- Test reali di transazione: batch con una citazione falsa non importa alcun candidato; pending non materializzato; strict merge atomico; allowlist non applicabile a output AI; review con testa obsoleta rifiutata; replay idempotente; correzione a nuova foglia; supporti multipli e revoca.
- Log Vega: 5 occorrenze indipendenti e zero conflitti.
- Temporalità: estrazione metadata/dichiarazioni separata dalla validità, precisione e timezone, DST ambiguo rifiutato, consolidamento pending, sorgenti duplicate non aumentano indipendenza, propagazione esplicita. 33 test complessivi passati.
- Checkpoint sorgenti/test/documentazione salvato su Drive (`dslm3_checkpoint.zip`), senza ambiente virtuale.
- Inizia step 06: selezione AI, package, import multiplo, export/diff e grafi.

## Step 06 e interfaccia

- Suite AI/export: 38 test passati, incluso doppio package con lo stesso candidate_id esterno, citazione falsa, staleness, conferma senza merge, successivo merge e conflitto reale, idempotenza snapshot, export GEXF/XSD offline, spells disgiunti.
- UI/API/CLI usano la stessa funzione di dispatch. Mini server vincolato a 127.0.0.1; controlli origin, host e token contro scritture cross-site. Test HTTP completo di upload → pipeline → review → merge → download, oltre a richieste vietate: 39 test passati.
- Casi SQL estesi hanno rilevato split errato dei membri package e DELIMITER MySQL: corretti. CTE non viene promossa a tabella fisica. Aggiunti sinonimi, database link, viste materializzate e colonne NEW/OLD del trigger. Suite estesa: 44 passati.
- Docling PDF: scaricati realmente modelli OCR; rilevata dipendenza SOCKS mancante richiesta dal proxy dell'ambiente. Installato httpx[socks] e ripresa conversione con modelli layout reali.
- Download Chromium della versione Playwright iniziale fallito con 502/timeout; in corso installazione di una versione stabile del solo headless shell per il collaudo browser. Il web generale/PyPI/HuggingFace/ModelScope sono raggiungibili; nessuna capacità simulata.

## Laboratorio Vega M3 — cicli di correzione

- Tentativo 01: registrazione fallita per evidenza identica prodotta da NEW/OLD sullo stesso locator; introdotta deduplicazione canonica prima della transazione e link parse/evidence idempotente.
- Tentativo 02: tutti i controlli funzionali superati fino al replay; lo schema DDL era inutilmente incluso nella propria chiave cache. Limitata la dipendenza da schema ai sorgenti SQL che ne hanno bisogno.
- Tentativo 03: 19/19 controlli passati. 6 fonti, 52 evidenze, 30 fatti, 24 relazioni, 1 conflitto di dominio P1, 1 intervallo. Zero falsi conflitti log, round-trip multiplo e riavvio verificati. Le risposte AI sono fixture controllate dichiarate, non chiamate a un modello esterno.
- PDF reale con OCR/layout/table models: conversione SUCCESS; testo atteso rilevato. Report `pdf_result.json`.
- Chromium headless stabile installato. Il primo test browser ha rilevato isolamento localhost fra invocazioni shell dell'ambiente; il server di test ora viene avviato nello stesso processo orchestratore. Corretto anche il polling del test per attendere davvero il completamento del job.

## Ripresa dopo disconnessione — stato effettivo

- Recuperato lo ZIP persistente precedente; le modifiche descritte nel protocollo integrativo non erano nei sorgenti recuperati.
- Ambiente Python 3.12 ricreato. Download PyPI e PyTorch raggiungibili. Dipendenze in installazione; nessun nuovo test dichiarato superato.
- Ripristinate le correzioni a interpretazioni correnti, cache riattivabile, identità deterministiche indipendenti dal corpus, appartenenza ai batch, stato partial, upload, YAML/ODS, temporalità e messaggi UI. Da collaudare.
- In corso ripristino dei casi SQL procedurali e del grafo arricchito.
- Su richiesta dell'utente il salvataggio prosegue per singoli file e cartelle su Drive, senza archivi ZIP. Il checkpoint precedente rimane una fonte storica.
- I report recuperati sono in reports/precedente: non sono prove della versione in corso.

### Ripresa — collaudo funzionale

- Prima suite: 43 passati e 1 errore nel vecchio conteggio degli spells GEXF; con l'aggiunta dei nodi fact e degli archi di provenienza la prova è stata aggiornata per controllare gli intervalli dei nodi fact, oltre alla validazione XSD.
- Suite estesa: 64 passati e 2 regressioni emerse (serializzazione millisecondi e marcatori Markdown con underscore). Corretti i sorgenti e ripetuta l'intera suite.
- Ultima suite conclusa: **78 passed**, 2 warning delle dipendenze di test, 37,33 secondi; reports/acceptance_tests.log. Conversioni worker reali CSV/TSV/JSON/JSONL/YAML/EML/MHTML/XLS/ODS/PPTX/HTML/SQL UTF-16.
- Vega eseguito in workspace nuovo: **19/19**, sei successi, 52 evidenze, 30 fatti, 24 relazioni, un conflitto P1 reale, un intervallo; reports/vega_release_01.json.
- Ambiente effettivo: Python 3.12.14, Docling 2.128.0, SQLGlot 30.18.0, PyTorch 2.14.0+cpu, NumPy 2.2.6 e OpenCV 4.12.0. Docling DOCX reale SUCCESS, 796 caratteri. pip check senza dipendenze incompatibili.
- Browser, PDF, documentazione e packaging ancora da chiudere. Nessuna scrittura su GitHub.

### Ultima regressione emersa dal PDF reale

Docling serializza `valid_from` come `valid\\_from` nel Markdown. La conversione PDF era riuscita, ma quella forma della dichiarazione temporale non veniva riconosciuta. Estesa l'estrazione mantenendo il testo originale e aggiunta una regressione dedicata; lo smoke PDF verifica ora anche `valid_from=2026-09-01`. Nessuna modifica alle fixture per nascondere il problema. Nuova suite, Vega e verifica wheel avviati sul sorgente corretto.

### Collaudo definitivo della ripresa

- **79 passed**, 2 warning di deprecazione dipendenze, 27,80 secondi; `reports/acceptance_tests_final.log`.
- Vega finale in workspace nuovo: **19/19**, conteggi invariati; `reports/vega_release_final.json`.
- PDF finale reale: SUCCESS e `valid_from` riconosciuto dal Markdown Docling; `reports/pdf_result_final.json`.
- Chromium finale: percorso completo, zero errori JavaScript. Schermate desktop, mobile e dialogo di review ispezionate; nessun overflow di pagina.
- Wheel installato in directory temporanea fuori dai sorgenti: sei fonti elaborate, UI e risorse XSD disponibili, grafo valido. Nuovo build dopo l'ultima correzione temporale e smoke ripetuto.
- Lint F superato, pip check senza incompatibilità, launcher shell verificati sintatticamente. Windows non eseguito.
- Manuale, architettura, limiti, avvisi sul riuso e README completati. Il salvataggio finale per singoli file è in corso; step 08 ancora aperto fino al controllo remoto.

### Chiusura e consegna

- Verificati tramite rilettura metadata Drive **141/141 file** del progetto: nomi e dimensioni corretti; tutti gli hash locali coincidono con gli hash registrati dopo gli upload. Evidenza: `reports/drive_verification.json`.
- Salvati sorgenti, test, fixture, risorse, manuali, report correnti e storico come singoli file, senza nuovi archivi ZIP. Gli aggiornamenti mantengono gli ID dei file Drive.
- Creato `START_HERE.md`; il vecchio documento nativo di ripresa è rinominato esplicitamente STORICO. Obiettivi, diario e matrice sono allineati anche nelle copie alla radice.
- `release_manifest.json` registra dimensioni e SHA-256 dei file della consegna; esclude cache, ambiente virtuale, workspace runtime e build intermedi.
- Step 08 chiuso: **rilascio 3.0.0 consegnato**, con 79 test passati, Vega 19/19 e limiti di piattaforma/formato dichiarati. Nessuna scrittura GitHub.

## 2026-09-18 — modifica proposta: workflow UI e workspace multipli

- Riesaminato il percorso UI E2E: il flusso reale non è lineare 01→06; AI e temporalità generano nuovi candidati che devono tornare al gate review → merge → reconcile.
- Preparata modifica per mostrare esplicitamente `00 → 01 → 02 → 03 → 02 → 04 → 02 → 05 → 06` e rinominare visivamente l'operazione globale come **Pipeline rapida**.
- Preparato registry locale multi-workspace con create/register/switch/forget non distruttivo e switch bloccato in presenza di job queued/running.
- `docs/protocollo_ripresa_precedente.md` resta storico; introdotto `docs/protocollo_ripresa.md` come protocollo corrente.
- Stato delle prove: **non ancora rieseguite su questa modifica**. I risultati 79 passed / Vega 19/19 / browser del 3.0.0 non devono essere attribuiti alla patch. Lo step 09 rimane aperto fino a suite, browser, Vega e rigenerazione del manifest.

## 2026-09-29 — upgrade del core deterministico

- Checkout inizialmente pulito sul branch richiesto, HEAD `a7117e061b393123e3b7b2ec22bf171687756447`. Il checkout v1 al commit `8b576eb605b2509ebe84785aae6b2d1e94046b8b` è stato usato soltanto in lettura, attraverso `git show`; le sue modifiche locali non sono state usate come oracle.
- Bootstrap su Windows 11 x64 con `C:\_Support\.venv_dslm3\Scripts\python.exe`, Python 3.12.10. Installazione editable `.[dev]`, dipendenze e Chromium reali. Il kit offline trovato contiene risorse Linux e non è stato usato per simulare prove Windows. Python 3.14 nel PATH non è stato utilizzato.
- Baseline locale: 89 test passati. Introdotti registro v4, componenti/applicabilità/risoluzione, resolver condiviso, DDL e DML canonici, contesto statement, attributi persistenti, Forms qualificati, chunk esatti e AI minima basata sulla copertura. Migrazione 3 con storico preservato e indice ricostruibile delle derivazioni correnti.
- Primo ciclo: adattati gli attesi che omettevano PK inline, la versione schema e la nuova motivazione di selezione AI. Rilevato e corretto un errore di sintassi nella costruzione del manifest AI.
- Il ciclo Windows con percorsi accentati ha rilevato la lettura del JSON worker con encoding implicito; impostato UTF-8. Ha poi rilevato auto-invalidazione della cache DDL locale; escluso lo schema locale dalla chiave esterna e aggiunto passaggio finale SQL sullo schema completo. Le sette prove encoding/rule-only/upgrade sono poi passate.
- Oracle indipendente: verificata perdita legacy di un separatore newline, documentata come eccezione corretta in v3. L'inferenza maps_to → writes_to della v1 non è stata adottata senza una modalità esplicita.
- Iterazione completa 01: 126 test passati; Vega deterministico, browser desktop/mobile e wheel passati. Il laboratorio integrato ha rilevato il budget fisso di due evidenze nel secondo package: corretto il test selezionando il budget dalla posizione dell'evidenza effettivamente citata. Il rapporto ha registrato PowerShell 7.6.6; G17 correttamente non verificato in quell'iterazione. I sorgenti sono stati ulteriormente corretti durante i controlli, quindi quella prova non certifica lo snapshot finale.
- Ulteriore revisione: hash dei file realmente installati anche senza Git, package body-only con precedenza della spec, colonne Forms già qualificate e mismatch strutturale, errori parser interni non mascherati, stato partial esplicito. Aggiunte sette prove mirate: tutte passate, incluse rinomina positiva di tabella/colonna/constraint, branch MERGE e ordine d'import.
- Avviata l'acceptance finale mediante invocazione esplicita di `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -File scripts/check_deterministic_core.ps1`; il JSON registra **5.1.26100.9444**. Report di checkpoint in `reports/deterministic_core/final`; nessuna prova storica riciclata. Nessun commit, branch aggiuntivo o scrittura remota.
- Iterazione Windows 5.1: 132 passati e 1 regressione. Togliere il catch generico ValueError aveva esposto anche il ValueError usato intenzionalmente per un costrutto fuori subset. Introdotta `UnsupportedStatement` e catturata soltanto quella diagnosi prevista; un ValueError interno continua a propagarsi. Le due prove mirate sono passate. Conservata l'iterazione fallita e arrestati soltanto i relativi processi di acceptance.
- Aggiunte e superate altre tre prove: DEFAULT NULL distinto da default assente e stringa 'NULL', PK SQLite senza falsa nullability, round-trip di SQL NULL/FALSE/stringa vuota Oracle/decimale esatto con rifiuto di payload malformati. La nuova esecuzione completa include anche queste prove.

### Chiusura storica del core — 29 settembre 2026

- Esecuzione `run_20260929_160037`, Windows 11 x64, PowerShell **5.1.26100.9444**, Python **3.12.10 x64**: **136 passed, 0 failed, 0 skipped**, 328,81 secondi, due soli avvisi di deprecazione delle dipendenze. Pip check e lint F passati.
- **G01–G18, COV-01–08, BIZ-01–08 tutti passed**. `reports/deterministic_core/final/acceptance.json` contiene nove comandi reali con exit code 0, prove e versioni; i dettagli COV/BIZ conservano attesi, osservazioni, candidate, locator e cicli di modifica.
- Vega senza AI **12/12**: 6 fonti, 56 evidence, 66 componenti; 62 supportate/applicabili/derivate, 4 evidence-only, zero mancanti/sconosciute/errori/blocchi. Quattro slot canonici presenti. Vega integrato **19/19** con AI controllata separata e un conflitto P1 atteso.
- Browser passato a 1440×1080 e 390×844, zero errori JavaScript. Schermate panorama desktop/mobile e dialogo review ispezionate. Build/installazione/smoke wheel fuori checkout passati su sei fonti reali.
- Hash dei sorgenti testati e del wheel installato identico: `bf94e472ffdbf04f7dffc7d62ec419da5a90461720ce78028a3dbfe7e50870d6` (42 file; Git assente nel wheel). Sorgenti invariati durante l'ultima acceptance.
- Documentazione chiusa; manifest 3.0.0 mantenuto storico e non certificante gli hash correnti. La patch è esportata con indici temporanei, verifica Git forward/reverse, senza alterare l'indice reale. Esiti/hash/inventario in `reports/deterministic_core/delivery.json`.
- Nessuna fixture Vega o implementazione vendor modificata, nessun ramo aggiuntivo, commit o scrittura remota. I limiti del subset SQL e dei backend non certificati restano espliciti nel rapporto corrente.


## Pass di chiusura — 30 settembre 2026

- Checkout inizialmente pulito su feat/deterministic-core-upgrade, HEAD
  53bf0c31638199c26fb86c1523018680bf9c34c1. Il lavoro principale è già committato.
  La baseline originaria e il padre rimangono a7117e061b393123e3b7b2ec22bf171687756447.
  Le annotazioni precedenti su commit e remoto descrivono soltanto il lavoro
  svolto il 29 settembre e non lo stato successivo del repository.
- G05: prova esplicita di pseudorecord, classificazione e schema incompatibile.
- Oracle v1 esteso senza leggere o cambiare il working tree v1. Il confronto
  evidenzia l'ordinamento improprio delle liste FK nel deriver v1: v3 conserva
  l'ordine originale. Nessuna normalizzazione distruttiva introdotta.
- Due lacune effettive chiuse: base parent nota per colonne mancanti nel resolver;
  identità Excel qualificate per scope/foglio e nome originale preservato.
  Versione workbook ooxml/2 e chiave cache pertinente, nessuna migrazione SQLite.
- G18 ora produce controlli nominati, hash, lettura dei report e revisione manuale
  documentata. Export patch corretto per HEAD successivo alla baseline.
- I primi test mirati hanno individuato errori nell'adattatore del confronto
  (chiave reason, data_type, foreign_key, filtro del producer Excel e scope
  workbook diverso dal foglio destinatario). Corrette le proiezioni senza
  rimuovere asserzioni semantiche. Nessun expected failure o skip aggiunto.
- Report della nuova acceptance in closure_20260930, separati da final/ storico.

- Primo ciclo completo del 30 settembre: 152 test passed, Vega 12/12 e 19/19,
  browser e wheel passed. G18 ha correttamente impedito una chiusura automatica:
  l'inventario includeva il database workspace/registry.sqlite3 già presente e
  invariato nella baseline (blob 3f0144953b93def5f9626af3a3dcd79e4bb6c998).
  Corretto lo scope del controllo per usare lo stesso delta della patch; nessun
  dato del workspace storico rimosso o alterato. Nuovi/modificati file runtime
  restano vietati, con un nuovo test negativo. Prova non conclusiva conservata
  in closure_20260930_gate_scope_01; nuovo collaudo integrale con harness corretto.

### Chiusura corrente verificata

- Run run_20260930_114524: **153 passed, 0 failed, 0 skipped**, 289,82 s pytest,
  2 avvisi di deprecazione; **G01–G18 e COV/BIZ tutti passed**. Nove comandi
  con exit code 0 su Windows 11 x64, PowerShell 5.1.26100.9444, Python 3.12.10 x64.
- Vega deterministico 12/12, integrato 19/19, browser desktop/mobile e wheel
  passati. Nuove schermate panoramica/mobile/review ispezionate.
- Snapshot applicativo (anche nel wheel): `b05c6c86037860bf92f7bce8cc72606d83b3a019bbb8f1c12cf3016eb4e09f84`.
  Snapshot eseguibile completo di 80 file: `14b4b0c8e16ce0da0945ff98ac8d34f8c579d355e01e67904a18b5add1265b51`.
  HEAD iniziale 53bf0c3 e baseline a7117e sono distinti da entrambi gli hash.
- Dopo il run vengono allineati solo documenti e revisione manuale; G18 viene
  rieseguito senza modificare o riassegnare le prove. Runtime storico già nella
  baseline preservato, escluso dalla patch; nessun file runtime nuovo consegnato.
- Nessun nuovo branch, merge, push o altra scrittura remota in questo pass.
