# Architettura DSLM3

## Struttura

| Modulo | Responsabilità |
|---|---|
| `service.py` | Acquisizione, scansione, worker isolato, evidenze correnti, stato e run |
| `storage.py` | SQLite, schema/migrazioni, transazioni e viste effettive |
| `parsers/` | Contratto parser comune; SQL, documenti, Forms, log e dati |
| `vendor/` | Algoritmi puri OOXML della baseline |
| `knowledge.py` | Candidati, citazioni, derivazione, review, correzioni, merge, supporti e conflitti |
| `temporal.py` | Segnali grezzi, precisione/timezone, concordanza, proposte e propagazione |
| `ai.py` | Piani spiegabili, pacchetti, integrità e import JSONL |
| `exports.py` | Snapshot, diff e GEXF validato offline |
| `web.py`, `static/` | FastAPI, coda seriale, protezioni localhost, UI HTML/CSS/JS |
| `cli.py` | Fallback CLI sullo stesso dispatch applicativo |
| `lab.py` | Laboratorio Vega riproducibile, con AI simulata esplicita |

## Flusso e confini

Il servizio copia i byte immutabili, registra fonte/revisione e avvia un solo tipo di worker parser. Il worker restituisce evidenze localizzate, diagnostica, stato e artefatti. Il parent controlla risorse e hash e registra la risposta in transazione. Una conversione non scrive direttamente fatti.

La derivazione e il rientro AI usano lo stesso contratto di candidato. Una review append-only modifica una testa transazionale; una correzione aggiunge una nuova foglia. Il merge materializza oggetti semantici e supporti. Le viste effettive richiedono almeno un supporto confermato, foglia, fonte attiva, revisione e interpretazione correnti.

La migrazione SQLite 2 aggiunge `current_parse` e l'appartenenza dei candidati ai batch. L'identità delle proposte deterministiche dipende dall'evidenza e dal contenuto, non dall'intero corpus: aggiungere una fonte non riapre review invariate. Riattivare un parsing in cache crea un nuovo record append-only. Gli schemi hanno checksum e la migrazione preserva i registri precedenti.

La storia resta disponibile; la revoca non cancella un oggetto fisico. La riconciliazione chiude il lavoro derivante da decisioni mutate e gli export normali ne verificano lo stato. Lo snapshot conserva supporti, citazioni, hash e sorgenti, separati dalle strutture semantiche.

## Semantica temporale

`temporal_raw` conserva segnali e natura della data. Gruppi e proposte non sono approvazioni. Gli intervalli diventano effettivi solo con review e merge. I metadata first_seen e ZIP non equivalgono a validità di dominio; precisione, envelope e timezone restano espliciti. I conflitti fra fatti con intervalli disgiunti vengono esclusi. La propagazione richiede un'operazione esplicita.

## Semplificazioni rispetto alla v1

Una sola API applicativa serve UI e CLI. Un solo worker ha il contratto parser comune. Oggetti e supporti usano tabelle comuni ai tipi semantici; merge, review e riconciliazione non hanno implementazioni duplicate. Il frontend non richiede un build Node. Sono riutilizzati soltanto gli algoritmi puri OOXML e le risorse GEXF, con attribuzione esplicita.

La parità è funzionale sugli scenari verificati, non sintattica per CLI/ID/schema o migrazione dei workspace v1. I limiti effettivi sono in `formati_e_limiti.md`; le prove in `reports` e `tests`.

## Protezioni e atomicità

Percorsi relativi validati, copie hashate, XML senza entity esterne, macro/link non eseguiti. Il web richiede host/origin locale e token sulle scritture. I job UI sono serializzati. SQLite usa WAL, foreign key, transazioni immediate e trigger append-only sui registri immutabili. Un batch candidato non valido non importa righe parziali. La configurazione e i file del corpus richiedono un solo processo mutante per workspace; non è implementato un lock interprocesso globale per l'acquisizione.
