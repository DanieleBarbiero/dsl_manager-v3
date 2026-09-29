# Rapporto del core deterministico — 29 settembre 2026

**Incarico completato nel subset dichiarato. G01–G18, COV-01–08 e BIZ-01–08
sono tutti passed**, senza test falliti o saltati. Comandi, exit code e prove sono
in `reports/deterministic_core/final/acceptance.json`.

Il lavoro resta sul branch `feat/deterministic-core-upgrade`, baseline/HEAD
`a7117e061b393123e3b7b2ec22bf171687756447`, padre `fix/vega-quality-backlog`.
Le modifiche sono locali e non committate; il rapporto registra `dirty=true` e
l'hash dei sorgenti eseguiti:
`bf94e472ffdbf04f7dffc7d62ec419da5a90461720ce78028a3dbfe7e50870d6`.
Lo stesso hash è ottenuto dai 42 file del pacchetto installato senza Git.
Non sono stati creati branch né effettuate scritture
remote. Il checkout v1 è stato letto senza alterarne il lavoro preesistente.

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

Suite completa corrente: **136 test passati**, 2 avvisi di deprecazione delle
dipendenze, 328,81 secondi. Vega deterministico: **12/12** controlli passati.
Laboratorio integrato **19/19**, browser desktop/mobile senza errori JavaScript,
build, installazione e smoke del wheel passati. Le schermate desktop, mobile e
dialogo di review sono state anche ispezionate. Tutti i nove comandi del runner
hanno exit code 0; lo snapshot applicativo è rimasto invariato durante la verifica.

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

- [Matrice G01–G18 e COV/BIZ](../reports/deterministic_core/final/acceptance.md),
  [dati e comandi effettivi](../reports/deterministic_core/final/acceptance.json),
  [JUnit completo](../reports/deterministic_core/final/pytest.xml).
- [Vega deterministico](../reports/deterministic_core/final/vega_deterministic.json),
  [Vega integrato](../reports/deterministic_core/final/vega_integrated.json),
  [browser](../reports/deterministic_core/final/browser/browser_result.json).
- [Business positivo](../reports/deterministic_core/final/business_audit.json),
  [negativo lessicale](../reports/deterministic_core/final/decrement_audit.json).
  `final/details/` conserva attesi e osservazioni di COV/BIZ prodotti dalle
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
SQL, macro o collegamenti esterni. XLSB e gli altri backend privi di fixture
dedicate restano non certificati; PDF/OCR completo conserva soltanto le prove
storiche del rilascio, senza attribuirle a questo collaudo.

La prova di upgrade costruisce un registro schema 2 usando storage/service/deriver
della baseline letti da Git, quindi verifica migrazione, storico, review e nuove
identità. Non è una migrazione del formato workspace v1. Nessun workspace operativo
dell'utente è stato alterato. La procedura opzionale per una copia a freddo reale
è documentata nel wrapper.

Il manifest di rilascio 3.0.0 è contrassegnato come storico e non certifica gli
hash correnti. Il numero versione del pacchetto non implica una nuova pubblicazione.
La [patch completa](../reports/deterministic_core/change.patch) è prodotta con
output Git binario e include i nuovi file pertinenti. `delivery.json` registra
hash, inventario e verifica della patch; patch e relativo checksum sono esclusi
dal proprio contenuto. Non sono inclusi ambienti virtuali o database runtime.

Le iterazioni fallite e i motivi di correzione restano nel diario e nei report
precedenti della stessa cartella. Solo `final/` certifica lo snapshot finale.
