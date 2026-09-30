# Copertura deterministica interrogabile

Contratto `4`, regole `4.0`, parser SQL `sql/4`, cache parser
`deterministic-parser/4`, migrazione SQLite `3`, package AI `4`.
Il catalogo eseguibile è in `src/dslm3/deterministic.py`: `PARSER_TYPES`,
`REGISTERED`, `CONSTRAINTS`, `STATEMENTS` e `RELATIONS`. Non usa wildcard per
accettare automaticamente nuovi tipi o subtype.

## Inventario e risultati

`Application.coverage(check=False)` restituisce il rapporto corrente.
`python -m dslm3 -w <workspace> coverage --check` esce con errore se ci sono
componenti sconosciute, risultati dovuti mancanti o errori parser. Il comando
`coverage` senza `--check` permette di ispezionare anche uno stato incompleto.
La stessa operazione è disponibile dal dispatch UI/API; Impostazioni mostra i
contatori. La derivazione restituisce il rapporto completo nel proprio risultato.
`complete` verifica classificazione e risultati dovuti; non approva le diagnosi di
risoluzione. `fully_derived` richiede inoltre zero blocchi e zero componenti non
supportate. La derivazione espone `status=partial` negli altri casi. Errori parser
di risorsa/formato e errori interni hanno contatori distinti; entrambi fanno fallire
il controllo. Le fixture positive devono confrontare anche gli esiti risolutivi.

Ogni evidence include formato, tipo, subtype, parser, locator e componenti.
Ogni componente include chiave locale, capacità, applicabilità, risoluzione,
regola/versione, prerequisiti, motivazione, fingerprint, candidate attese e
candidate riscontrate, con la loro review. Gli attesi si costruiscono dalla
struttura del parser prima di cercare le candidate nel ledger.

| Dimensione | Valori |
|---|---|
| Capacità | `supported`, `evidence_only`, `unsupported`, `unclassified` |
| Applicabilità | `applicable`, `blocked_by_resolution`, `not_required` |
| Risoluzione | `not_required`, `resolved`, `unresolved`, `ambiguous`, `inconsistent` |
| Risultato | `materialized_deterministically`, `due_missing`, stato bloccato, `evidence_only_by_design`, `unsupported_with_reason`, `unclassified` |
| Evidence composita | `partial` quando gli esiti delle componenti differiscono |
| Governance | `pending`, `confirmed`, `rejected`, `superseded`; separata dal risultato tecnico |

`expected_components` è il totale. `supported_components` contiene applicabili e
bloccate. `due_applicable_components` comprende `derived_components` e
`due_missing_components`. I tre contatori `blocked_*_components` sono distinti.
Non sommare questi sottoinsiemi al totale come categorie indipendenti. Una
componente che richiede più risultati conta una sola volta e passa solo se sono
presenti tutti. Candidate e oggetti sono conteggi separati. Il rapporto corrente
esclude revisioni, parse e risultati tecnicamente superati; il ledger storico resta.

Un blocco giustificato non è un difetto di derivazione applicabile, ma non è
nemmeno una relazione risolta. Il controllo di acceptance confronta le diagnosi
con attesi indipendenti: un `unresolved` in una fixture positiva fallisce.
`require_complete(report, expected_resolution)` supporta questo controllo senza
nomi di fixture nel servizio.

## Subset e shape

| Famiglia | Risultato canonico |
|---|---|
| Tabella / altri oggetti DDL | `object_type` con attributi strutturati; view/materialized view mantengono query e dipendenze |
| Colonna | `database_column/data_type`, datatype AST, dichiarazione e base di nullability, default presente/assente e AST, constraint |
| Constraint PK/FK/UNIQUE/CHECK | Un fatto `constraint` distinto per identità; FK conserva ordine e estremità grezze anche senza target |
| FK risolta | Relazione `foreign_key`, `columns` e `target_columns` ordinate, identità constraint |
| Index/unique index | Oggetto index con tabella, flag unique ed espressioni ordinate; relazione `indexes` risolta |
| ALTER ADD CONSTRAINT | Dichiarazione osservata e constraint; le altre ALTER restano unsupported motivate |
| Code unit | `unit_type`; package spec/body distinti, membri dichiarati e firma; scanner non compila PL/SQL |
| UPDATE | `statement_structure`, una componente per SET, `assigned_value` tipizzato oppure solo RHS `assignment_expression`, WHERE completo se presente |
| INSERT | Colonne esplicite e mapping ordinato di VALUES o SELECT con proiezioni ad arità nota; righe e branch distinti |
| DELETE | Target, presenza di WHERE e predicato completo |
| MERGE | Target/source, ON, branch/action AST e assegnazioni con contesto branch |
| SELECT | Proiezioni strutturate, alias/CTE/subquery e dipendenze fisiche determinabili; nessuna espansione arbitraria di `*` |
| CALL/EXEC e chiamate statiche | `calls` solo verso dichiarazione risolta; le intrinsic Oracle nominate restano fatti di chiamata sintattica |
| Forms | Identità FORM.BLOCK.ITEM anche per field/button; `uses_table`, `maps_to`, `calls`; read/write solo con modalità esplicita non contraddittoria |
| Log | Evento per occorrenza, fatto `occurrence` observed e relazione `observed_on`; righe non riconosciute conservate |
| Excel | Manifest OOXML immutato, fatti strutturati con formule/cache/celle separate, riferimenti esterni espliciti senza dereferenziazione |
| CSV/JSON/YAML/email/XML generico | Record strutturali interrogabili; chunk di testo separati |
| Testo libero / codice Forms | Evidence-only con motivazione; non attribuisce business non codificato |

Rappresentazione literal: `{type: string|number|boolean|null, value: ...}`.
I numeri sono stringhe decimali esatte, booleani sono booleani JSON e SQL NULL è
`{type: null, value: null}`. Oracle stringa vuota conserva anche
`source_literal: empty_string`; PostgreSQL distingue la stringa vuota.
Funzioni, CAST e literal tipizzati non vengono valutati. PK non implica
universalmente NOT NULL: la conseguenza è applicata ai dialetti esplicitamente
elencati dalla regola, con eccezione SQLite conservata.

Ogni operazione espone `attributes.context` (owner, statement, componente,
eventuale branch). Semantic key, merge, conflitti, diff e snapshot conservano
questo contesto. `fact_type` e gli attributi semantici fanno parte dell'identità.
La provenance amministrativa e i supporti sono separati: fonti indipendenti
possono supportare lo stesso oggetto dichiarativo.

## Motivazioni stabili principali

`unique_declaration`, `target_absent`, `multiple_targets`,
`column_parent_ambiguous`, `foreign_key_arity`,
`foreign_key_ambiguous_endpoint`, `foreign_key_missing_endpoint`,
`foreign_key_target_key_unknown`, `foreign_key_endpoints_verified`,
`contradictory_access_mode`, `syntactic_extraction`,
`free_text_requires_interpretation`, `forms_code_analyzer_not_enabled`,
`syntax_not_analyzed`, `unrecognized_log_line`, `tuple_assignment`,
`insert_implicit_columns`, `insert_projection_arity`,
`alter_outside_add_constraint`, `dynamic_sql_not_executed`,
`unregistered_type_or_subtype`.

Le varianti fuori subset conservano evidence e confini. SQL dinamico non viene
eseguito e non genera target dalle stringhe. Il parser cattura soltanto gli errori
di sintassi previsti; gli errori interni arrivano al worker come errori, senza
essere trasformati in successi evidence-only.

## Persistenza, upgrade e AI

La migrazione 3 conserva le migrazioni 1 e 2 con i checksum originali.
`deterministic_active` è un indice tecnico ricostruibile, non una review. Si
ricostruisce all'apertura e dopo ingest, scan, parse e derivazione usando gli
output attesi nel contesto corrente. `current_derivation` completa i criteri delle
viste effettive e segue la radice anche nelle correzioni umane. Le vecchie review
non vengono cancellate o trasformate in revoche tecniche. Una fonte target
modificata o rimossa rende subito inefficaci i supporti dipendenti.

La cache include versioni/configurazione e schema per ogni DML, anche standalone.
Le dichiarazioni locali vengono riconosciute prima delle dipendenze; il servizio
completa il parsing SQL sullo schema disponibile dopo l'import del corpus.
Le candidate usano fingerprint del riferimento pertinente, non dell'intero corpus.

La selezione AI tecnica esclude evidence completamente derivate anche pending o
rejected. I package 4 espongono copertura e componenti residue, e rifiutano il
rientro tecnico che duplica una componente deterministica corrente. La route di
dominio resta disponibile a budget sufficiente; non è necessaria per estrarre
CHECK, literal ammessi o limiti numerici espliciti.

## Prove e riferimenti

`test_deterministic_core.py` collega COV-01–08 e BIZ-01–08; i test di lifecycle
aggiungono Windows, migrazioni, rule-only, cache e governance dei residui.
`test_deterministic_oracle.py` legge i moduli v1 dal commit
`8b576eb605b2509ebe84785aae6b2d1e94046b8b`, senza modificare il checkout v1.
Golden OOXML e fixture business hanno attesi indipendenti.
Le prove correnti e i comandi sono in `reports/deterministic_core/closure_20260930`;
`final/` conserva la prova storica del 29 settembre. La chiusura G05/G15/G18
è descritta in `oracle_v1_chiusura.md` e `closure_checks.json`;
le iterazioni precedenti documentano anche errori e correzioni e non certificano
lo snapshot finale.


## Residui chiusi con prove nominate

G05 è collegato a `test_trigger_new_old_g05_table_binding_and_schema_diagnostics`.
G15 comprende i confronti diretti di schema_resolution e candidate_derivation
(slices21/25/32), oltre agli oracle DDL/DB/XML/chunk precedenti. La matrice
`oracle_v1_chiusura.md` distingue informazioni conservate, rappresentazioni v3
più complete, difetti v1 dimostrati e dettagli amministrativi non applicabili.
G18 verifica artefatti e provenienza, non soltanto exit code; i controlli manuali
sono espliciti in `revisione_chiusura_core.json` e legati allo snapshot esaminato.
