# Matrice di parità v1 → DSLM3

Baseline verificata nel codice e nell'analisi tecnica v1. I nomi dei moduli sotto sono le responsabilità progettate; lo stato effettivo è negli obiettivi e nei report di test. Una nuova UI/CLI non implica compatibilità sintattica con i comandi legacy. I dati runtime v1 non vengono modificati in-place.

| Capacità v1 | Contratto da conservare | Implementazione M3 / verifica richiesta |
|---|---|---|
| Workspace/config/log | Directory autonome, SQLite transazionale, configurazione validata, log e run | `storage.py`, `service.py`, config JSON standard al posto di YAML parziale |
| Scan | Ricorsione, revisioni SHA-256, fonti attive/mancanti, esclusioni | Copia immutabile dei byte, scansione idempotente, modifica/rimozione/replay |
| Worker | Isolamento, timeout, output budget, errori/partial visibili | Un worker con registry dei parser; stato per revisione e retry |
| Docling | Normalized JSON + Markdown + chunk localizzati | Docling reale 2.128.0, DOCX/XLSX/PDF e ulteriori formati ammessi |
| DDL | Tabelle, colonne, PK, FK e riferimenti risolti | AST SQLGlot, oggetti aggiuntivi e dialetti espliciti |
| DB code | Routine/trigger e dipendenze con locator | Scanner lessicale delle unità + AST SQL incorporato, scope subquery/alias; incerto non qualificato arbitrariamente |
| Forms XML | Form, campi, pulsanti, operazioni | Alias `item`/`field`, namespace, Oracle Forms export, `operation` e table usage |
| Log | Eventi osservati e provenance | Ogni occorrenza è un'entità-evento; nessuna falsa proprietà monovalore del componente |
| Workbook | Stessi byte, preflight, formule/cache separati, fogli/regioni/named range/tabelle/link/VBA hash | Riuso esplicito dei tre moduli puri v1; golden manifest invariato; macro/link non eseguiti |
| Formati extra | Estensione parser senza perdita silenziosa | CSV/TSV/JSON/JSONL/YAML/TXT/MD/HTML/XML, EML/MHTML, XLS/ODS/XLSB e Docling; limiti per formato dichiarati |
| Derivazione | Regole versionate, candidati pending, mai fact diretti | Un solo contratto di candidato per parser e AI |
| Review | Attore stabile, allowlist, testa, idempotenza, concorrenza | Review append-only + head in transazione; correzione crea nuova foglia |
| Merge | Solo foglie confermate, strict atomico, supporti multipli | `knowledge.py`; pending/rejected esclusi e confermati non ancora fusi visibili |
| Reconcile | Revoche/correzioni e storia preservata | Supporti effettivi dinamici e gate sugli export finché reconcile aperto |
| Conflitti | Valori incompatibili realmente applicabili allo stesso soggetto | Separazione evento/stato, intervalli non sovrapposti esclusi, conflitti tracciabili |
| Temporalità grezza | OOXML/ZIP/PDF/HTML/JSON-LD/dichiarazioni/nome/first_seen | Segnali, affidabilità, timezone, nessun mtime/ctime semanticizzato |
| Temporalità governata | Concordanza/indipendenza, conflitti, precisione anno/mese/giorno/istante | Envelope inclusivi, UTC/offset preservati, timestamp naive non confermabili |
| Propagazione | explicit_copy/intersection/aggregation/conflict, sempre pending | UI/API/CLI esplicite; niente eredità automatica della fonte |
| Supporti temporali | Intervallo con molteplici supporti correnti | Identità semantica separata dai candidati |
| Selezione AI | technical_extraction e domain_interpretation, coverage, rank e motivi | Piani immutabili, budget effettivi, controllo staleness |
| Handoff AI | Schema, template, contenuto, manifest, nessuna chiamata AI implicita | Package ZIP e round-trip multiplo; JSONL verificato rispetto al package |
| Candidate types | fact, relation, mapping, conflict, question, temporal_interval | Tipi supplementari conservati senza promozione implicita |
| DSL | Snapshot JSON/YAML/Markdown con hash e traceability; profilo statico e temporale | Schema M3 con profilo v1/v2; ID nuovi e documentati, output deterministico |
| Diff | Delta strutturale/governance/temporale, cross-schema esplicito | Diff con provenance e hash |
| GEXF | Statico e 1.3 dinamico, spells, date/dateTime, strict/omit/separate | Risorse XSD offline e verifica semantica dei limiti degli archi |
| UI locale | Consultazione + azioni sui passaggi | UI primaria completa, API comune alla CLI, stati e provenienza leggibili |
| Diagnostica | partial controllato senza alterare produzione | Diagnostica nel namespace test, errore distinto dal risultato valido |

## Scelte di semplificazione

- Eliminazione della catena CLI → worker specifico → file intermedi → registry specifico per ogni caso. Un worker produce lo stesso contratto parser; un solo servizio applica la transazione.
- Una sola tabella per oggetti semantici e una per supporti, con viste effettive; mantiene distinti i tipi senza duplicare merge/reconcile.
- Nessun framework frontend o build Node obbligatorio: HTML/CSS/JavaScript locale e FastAPI.
- Conservazione mirata di preflight, manifest OOXML e region detection v1: 3 moduli puri, non l'intero motore legacy.
- Gli stati UI mostrano separatamente estratto, proposto, confermato, consolidato e gli eventuali errori. La UI non elimina il confine di review.

## Gate Vega

Sei fonti originali processate realmente; due tabelle/nove colonne; quattro campi Forms e chiamata al procedimento; cinque occorrenze log senza conflitti reciproci; nessuna falsa colonna `ARTICOLO.ID_RICHIESTA`/`ARTICOLO.RICHIESTA_RICAMBIO`; manifest Excel e testo Docling reali; risposta AI simulata dichiarata → import pending → conferma → merge → DSL; revoca/correzione/idempotenza; segnali temporali pending e propagazione esplicita; export e diff; browser.

## Verifiche della consegna 3.0.0

La matrice descrive capacità funzionali e non compatibilità degli ID o migrazione automatica. I riferimenti eseguibili sono `test_parsers.py` e `test_formats_real.py` per i parser, `test_knowledge.py` per review/merge, `test_temporal.py` e `test_resume_regressions.py` per temporalità e ripresa, `test_ai_exports.py` per round-trip e grafi, `test_web.py` e `scripts/browser_check.py` per UI/API. La suite finale ha 79 test superati; Vega finale 19/19. `formati_e_limiti.md` distingue formati realmente testati, backend disponibili e coperture non certificate.
