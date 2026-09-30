# Rapporto di chiusura del core deterministico — 30 settembre 2026

Il pass di chiusura riguarda G05, G15, G18 e la provenance. Il risultato corrente
è registrato in `reports/deterministic_core/closure_20260930/acceptance.json`;
il collaudo completo è stato rieseguito, senza riutilizzare esiti storici.

- Baseline originaria: `a7117e061b393123e3b7b2ec22bf171687756447`.
- Branch corrente: `feat/deterministic-core-upgrade`.
- Branch padre: `fix/vega-quality-backlog`, ancora alla baseline originaria.
- Commit di partenza di questo pass: `53bf0c31638199c26fb86c1523018680bf9c34c1`.
- Snapshot applicativo effettivamente testato (42 file):
  `b05c6c86037860bf92f7bce8cc72606d83b3a019bbb8f1c12cf3016eb4e09f84`.
- Snapshot eseguibile completo (80 file, inclusi test, fixture, build e runner):
  `14b4b0c8e16ce0da0945ff98ac8d34f8c579d355e01e67904a18b5add1265b51`.
  `executable_snapshot.files` registra ogni SHA-256. HEAD e working tree sono
  campi distinti: questi test attestano lo snapshot, non il solo commit iniziale.

Il lavoro principale è già presente nel commit di partenza. Questo pass introduce
modifiche locali successive, descritte sotto. Non deduciamo la storia dei push
dallo stato locale: il vincolo operativo di questo pass è nessun merge, nuovo
branch o scrittura remota.

La directory `reports/deterministic_core/final/` conserva immutate le prove
**storiche del 29 settembre**: 136 test sul working tree dirty con HEAD a7117e,
snapshot applicativo `bf94e472ffdbf04f7dffc7d62ec419da5a90461720ce78028a3dbfe7e50870d6`.
Quelle prove non sono attribuite al commit 53bf0c3, né alla chiusura corrente.

## Modifiche di questo pass

- G05: acceptance esplicita di :NEW/:OLD, binding alla tabella del trigger,
  reads_from/writes_to, assenza di entità fisiche NEW/OLD e diagnostica delle
  colonne incompatibili; collegamento nominato nel runner.
- G15: oracle esteso a schema_resolution, candidate_derivation e slice21/25/32,
  eseguiti da sorgenti v1 pinned; [matrice puntuale](oracle_v1_chiusura.md) e
  [inventario SHA-256](oracle_v1_inventory.json). Nuove prove di deduplica,
  governance, FK, scope SQL, eventi, Excel e rappresentazione multivalore.
- Correzioni emerse dall'oracle: il resolver conserva il parent noto per una
  colonna assente; i named range e le tabelle Excel hanno identità qualificate
  per workbook/scope/foglio. Il nome originale resta in object_name. Il contratto
  workbook ooxml/2 invalida la cache pertinente, senza cambiare lo schema SQLite.
- G18: controlli verificabili su branch/baseline/snapshot, diff, documenti,
  release_manifest, file consegnabili ed esiti supportati da JUnit/report/log.
  I controlli manuali sono nominati in `docs/revisione_chiusura_core.json`,
  associati agli hash esaminati; non sono pass impliciti dall'exit code.
- L'export della patch usa ora il commit testato e include tutte le differenze
  dalla baseline, comprese quelle già committate. Non modifica l'indice reale.

## Stato delle verifiche correnti

**Chiusura verificata: G01–G18, COV-01–COV-08 e BIZ-01–BIZ-08 tutti passed.**
Run `run_20260930_114524`, Windows 11 x64, PowerShell **5.1.26100.9444**, Python
**3.12.10 x64** del progetto. Suite completa **153 passed, 0 failed, 0 skipped**,
289,82 secondi di pytest (293,563 secondi del comando), due avvisi di deprecazione
delle dipendenze. Nessun xfail aggiunto o risultato unsupported promosso a derived.

| Verifica corrente | Risultato |
|---|---|
| Pip check / lint F | Passed |
| Suite completa | 153/153 |
| Vega deterministico, senza AI | 12/12; quattro slot, zero gap o blocchi inattesi |
| Vega integrato, AI controllata dichiarata | 19/19 |
| Browser Chromium | Desktop 1440×1080 e mobile 390×844; zero errori JavaScript |
| Build, installazione e smoke wheel fuori checkout | Passed; sei fonti reali, coverage completa |
| Provenienza wheel / checkout | Stesso hash applicativo dei 42 file |
| G18 | 8 controlli automatici e 3 revisioni manuali nominate, con evidenze e hash |

Tutti i nove comandi hanno exit code 0. Sorgenti, test e runner sono rimasti
invariati durante l'esecuzione; i successivi aggiornamenti sono soltanto documentali.
Le schermate correnti desktop/mobile e dettaglio review sono state ispezionate.
La finalizzazione G18 aggiorna gli hash dei documenti senza riassegnare i test a
un altro commit o snapshot eseguibile.

## Test aggiunti e ciclo di correzione

**17 casi di test aggiunti**: 8 in `test_deterministic_closure.py` (trigger G05,
inventario oracle pinned, resolver, deriver slice21, Excel slice25, scope/eventi
slice32, rappresentazione multivalore e cache workbook), 9 in
`test_acceptance_closure.py` (runtime vietati, gate senza prova JUnit, modifiche
a test/runner e distinzione fra runtime storico invariato e runtime nel delta).
La [matrice G15](oracle_v1_chiusura.md) collega ciascun invariante alle prove.

Il primo ciclo completo aveva 152 test e tutti i comandi passati, ma G18 failed:
l'inventario considerava anche `workspace/registry.sqlite3`, già nella baseline e
invariato. Lo scope è stato corretto per coincidere con quello della patch, con
un nuovo test negativo. Il ciclo non conclusivo è conservato in
`reports/deterministic_core/closure_20260930_gate_scope_01/`; **la successiva suite
integrale da 153 test certifica anche l'harness corretto**. Nessun fallimento è
stato trasformato in expected failure, skip o unsupported per chiudere il gate.

## Risultato implementato

Il contratto v4 separa inventario delle componenti attese, supporto, applicabilità,
risoluzione, derivazione e review. Un tipo sconosciuto o un risultato applicabile
assente fallisce il controllo; una FK mancante conserva la dichiarazione e un
blocco motivato, senza relazione inventata. I test distinguono intenzionalmente
un blocco atteso da un errore risolutivo su fixture positiva. Contatori, ragioni,
basi, fingerprint, candidate e locator sono consultabili da API/CLI e nei report.

DDL e DML preservano datatype, default, nullability, vincoli, ordine delle FK,
literal esatti e AST interrogabili. Owner, occorrenza e ramo fanno parte del
contesto operativo fino a merge, conflitti, snapshot e diff. Il resolver condiviso
gestisce dichiarazioni correnti, ambiguità, incompatibilità e invalidazione dei
supporti dipendenti. Forms distingue F.B.ITEM, mapping, chiamate e modalità
esplicite. Chunking ricostruisce esattamente il normalizzato, inclusi whitespace;
log e manifest OOXML mantengono le rispettive identità e strutture.

La migrazione SQLite 3 preserva registri e decisioni; la cache include versioni,
configurazione e dipendenze. La selezione AI tecnica usa le componenti già
derivate anche pending/rejected; residui e route di dominio rimangono visibili.
Nessun contributo AI è necessario per il laboratorio deterministico o i CHECK
business. Il laboratorio integrato mantiene separatamente l'AI simulata dichiarata.

## Prove riproducibili

I risultati quantitativi correnti sono nel report eseguibile collegato sotto.

| Contatore Vega | Ottenuto |
|---|---:|
| Fonti / evidence correnti | 6 / 56 |
| Componenti inventariate | 66 |
| Supportate / dovute applicabili / derivate | 62 / 62 / 62 |
| Evidence-only motivate | 4 |
| Dovute mancanti / sconosciute / errori interni | 0 / 0 / 0 |
| Unresolved / ambiguous / inconsistent | 0 / 0 / 0 |

Non sommare i sottoinsiemi: i 62 risultati applicabili sono già compresi nei 66
componenti. I quattro slot attesi coincidono con quelli ottenuti: assegnazione
stringa tipizzata PRENOTATA a RICHIESTA_RICAMBIO.STATO; filtro ID_RICHIESTA;
RHS QTA_DISPONIBILE - 1 su ARTICOLO; filtro ID_ARTICOLO con subquery completa.

- [Matrice G01–G18 e COV/BIZ](../reports/deterministic_core/closure_20260930/acceptance.md),
  [dati e comandi effettivi](../reports/deterministic_core/closure_20260930/acceptance.json),
  [JUnit completo](../reports/deterministic_core/closure_20260930/pytest.xml).
- [Vega deterministico](../reports/deterministic_core/closure_20260930/vega_deterministic.json),
  [Vega integrato](../reports/deterministic_core/closure_20260930/vega_integrated.json),
  [browser](../reports/deterministic_core/closure_20260930/browser/browser_result.json).
- [Business positivo](../reports/deterministic_core/closure_20260930/business_audit.json),
  [negativo lessicale](../reports/deterministic_core/closure_20260930/decrement_audit.json).
  `closure_20260930/details/` conserva attesi e osservazioni di COV/BIZ prodotti dalle
  asserzioni eseguite, incluse mutazioni, rinomina, ciclo dei target e review.
- [Wrapper Windows](../scripts/check_deterministic_core.ps1) e
  [procedura](verifica_core_windows.md), [contratto](contratto_deterministico.md),
  [registro di copertura](copertura_deterministica.md).

Ambiente: Windows 11 x64, Python 3.12.10 x64 del progetto, PowerShell
5.1.26100.9444. SQLGlot 30.18.0, Docling 2.128.0, Playwright 1.56.0;
pin applicativi invariati. I processi worker, DOCX/XLSX reali, Chromium e wheel
sono eseguiti, non simulati. I test v1 eseguono moduli letti dal commit
`8b576eb605b2509ebe84785aae6b2d1e94046b8b`.

| Precisazione | Gate collegati |
|---|---|
| COV-01–05, COV-08 | G01; risoluzione anche G06 |
| COV-06, COV-08 | G06, G13; invalidazione e cache |
| COV-07 | G01, G12, G14; copertura separata dalla review |
| BIZ-01–02 | G02, G14, G15; struttura e oracle indipendente |
| BIZ-03–04 | G03, G14; presenza tecnica e assenza d'inferenza lessicale |
| BIZ-05 | G11, G13, G14; mutazione, effettività e diff |
| BIZ-06–08 | G11, G12, G14, G18; assenza AI, governance, provenance e report |

## Attesi business e confini

| Fonte | Informazione estratta | Inferenze vietate |
|---|---|---|
| `business.sql`, Oracle | STATO IN BOZZA/CONFERMATO/ANNULLATO; TOTALE >= 0; precisione 12,2; NOT NULL separati | Transizioni workflow, attori autorizzati, valuta, significato contabile, stato dei dati runtime |
| Variante strutturale | Quarto literal SOSPESO, limite 10, rimozione NOT NULL: payload effettivi e diff cambiano | Riuso del vecchio contenuto soltanto perché il nome è uguale |
| Variante rinominata | Tabella T, colonne X/Y/K, constraint C1/C2: stessi operatori e literal | Dipendenza della regola dal significato del nome |
| `decrement.sql`, Oracle | RHS `QTA_DISPONIBILE - 1`, WHERE con bind; rinomina conserva la struttura | Prenotazione, esaurimento scorte, unità di misura o autorizzazioni desunte dall'etichetta |

Le fixture e gli attesi JSON sono scritti indipendentemente dal deriver. La review
di test è esplicita, con attore e motivo; il merge iniziale con sole pending resta
vuoto. Provenance e locator restano collegati alle fonti dopo riapertura ed export.

## Eccezioni, limiti e consegna

L'oracle v1 perde un separatore newline nella fixture di chunking: v3 conserva
tutto il testo. La derivazione legacy di writes_to dal solo mapping Forms non
viene riprodotta; occorre una modalità esplicita. Queste differenze sono verificate,
non normalizzazioni introdotte per nascondere perdite.

Il subset SQL non è un compilatore procedurale universale. SQL dinamico, tuple
assignment, INSERT senza colonne e arità indeterminate rimangono esplicitamente
parziali. Gli overload ambigui non sono scelti arbitrariamente. Non si eseguono
SQL, macro o collegamenti esterni. Non applicabili a questo pass: sintassi CLI e ID amministrativi v1, migrazione
di workspace v1 e certificazione di piattaforme diverse da Windows. La matrice
G15 motiva ogni sostituzione di rappresentazione.
XLSB e gli altri backend privi di fixture
dedicate restano non certificati; PDF/OCR completo conserva soltanto le prove
storiche del rilascio, senza attribuirle a questo collaudo.

La prova di upgrade costruisce un registro schema 2 usando storage/service/deriver
della baseline letti da Git, quindi verifica migrazione, storico, review e nuove
identità. Non è una migrazione del formato workspace v1. Nessun workspace operativo
dell'utente è stato alterato. La procedura opzionale per una copia a freddo reale
è documentata nel wrapper.

Il manifest di rilascio 3.0.0 è contrassegnato come storico e non certifica gli
hash correnti. Il numero versione del pacchetto non implica una nuova pubblicazione.
La [patch completa](../reports/deterministic_core/closure_20260930/change.patch) è prodotta con
output Git binario e include i nuovi file pertinenti. `delivery.json` registra
hash, inventario e verifica della patch; i contenitori change.patch storici e
la patch corrente con il proprio delivery.json sono esclusi dal contenuto,
per evitare annidamenti e riferimenti circolari. Non sono inclusi ambienti virtuali o database runtime.

Le iterazioni e i motivi di correzione restano nel diario e nei report
precedenti della stessa cartella. `final/` rimane storico; solo `closure_20260930/` identifica il nuovo collaudo.


Durante la chiusura G18 il checkout conteneva ancora il workspace storico già
tracciato nella baseline, compreso `workspace/registry.sqlite3`; quella prova lo
registrava come runtime preesistente invariato e fuori dal delta del core.
Successivamente, nel commit `fd520b1` sul branch Vega, `workspace/` è stato
rimosso dal versionamento e aggiunto a `.gitignore`, senza cancellarne la copia
locale. Il workspace è quindi runtime locale e non fa parte della consegna da
promuovere a `main`. Questo cleanup non modifica il core certificato e rende
storico il precedente riferimento G18 al workspace versionato.


Il controllo whitespace di sorgenti, test, harness e documentazione è pulito.
Il comando grezzo sul diff completo restituisce 2 per righe di contesto delle
patch e output di test storici: `diff_check_all.txt` conserva quelle segnalazioni.
La revisione manuale distingue questi artefatti dai sorgenti senza riscrivere le
prove storiche. La patch di trasporto viene verificata con Git in indici isolati,
in applicazione sulla baseline e in applicazione inversa; l'indice reale resta
invariato. `delivery.json` contiene inventario, hash e controlli della consegna.
