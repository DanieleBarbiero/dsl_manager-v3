# Contratto deterministico 4

Il parser SQL/4 conserva citazioni originali e produce strutture AST serializzabili.
Il registro `dslm3.deterministic` inventaria componenti prima della materializzazione.
Ogni componente separa capacità, applicabilità, risoluzione, risultato e governance.
`materialized_deterministically` significa candidato prodotto/riusato, anche pending
o rejected: non significa review né merge. Le componenti bloccate da riferimenti
assenti, ambigui o incompatibili restano nel denominatore e sono rendicontate
separatamente dalle derivazioni dovute ma mancanti. Le attese delle fixture sono
esterne al servizio. Un errore interno non è un limite del formato.

Le colonne hanno un solo fatto `database_column/data_type`, con attributi di
datatype, nullability dichiarata, default tipizzato e constraint. I constraint
sono fatti distinti identificati da nome oppure hash strutturale. Le FK conservano
sempre la dichiarazione, e producono una relazione solo dopo risoluzione completa
di entrambe le estremità e delle colonne ordinate. CHECK e NOT NULL sono separati.
La proiezione AST dei CHECK rende operatori e literal interrogabili senza LLM;
non afferma che dati reali soddisfino quei vincoli e non deduce workflow dai nomi.

SQL: UPDATE/DELETE, INSERT con colonne e VALUES oppure SELECT ad arità esplicita,
MERGE con branch, SELECT con proiezioni esplicite, chiamate statiche. Espressioni
e predicati sono conservati senza esecuzione. `*` resta una proiezione non espansa.
NULL, booleani, stringhe e decimali hanno tipi distinti; i numeri sono stringhe
decimali esatte. Oracle stringa vuota è NULL con spelling originale conservato.
CAST, funzioni e literal tipizzati restano espressioni, mai valori calcolati.
Ogni slot operativo include owner, occorrenza statement, branch e componente.
I conflitti confrontano lo stesso slot e contesto, non operazioni diverse.

Il resolver legge dichiarazioni correnti indipendentemente dalla review; restituisce
resolved/unresolved/inconsistent/ambiguous, riferimento originale, alternative,
evidence di base e fingerprint. Le identità SQL quoted conservano case e segmenti.
Una menzione non dimostra l'esistenza. La sintassi DML resta estraibile senza schema.
Le dipendenze validate sono ricalcolate quando cambiano le fonti. L'indice tecnico
di attività è ricostruibile; evidence, candidati, review e supporti restano append-only.
La migrazione 3 aggiunge questo indice senza modificare checksum precedenti.

Le nuove shape portano `deterministic_contract=4` e regola/versione separati.
Workspace precedenti: conservare una copia a freddo, riaprire, analizzare e derivare;
le nuove proposte restano pending secondo la policy configurata. Le decisioni
precedenti sono storiche e tornano efficaci solo se il medesimo risultato è attuale.
Gli export conservano attributi, contesto, confidence e locator.

Chunk: testo normalizzato decodificato, range di caratteri [inizio,fine), massimo
5000 di default, strategia heading/paragraph, minimo configurabile. Testo ricostruito
esattamente inclusi whitespace; vuoto produce zero chunk. Heading nei fenced code
non contano; il contesto ripetuto è metadato. Byte originali e hash restano nella
revisione: ricostruzione del normalizzato non significa identità dei byte.

Le policy sono allowlist nominate; non autorizzano AI né consolidamento impliciti.
La selezione tecnica usa la copertura per componente; il dominio può usare anche
evidence già coperte. Un rifiuto non si aggira con una nuova estrazione AI.
I limiti dei backend documentali già dichiarati restano in `formati_e_limiti.md`.
