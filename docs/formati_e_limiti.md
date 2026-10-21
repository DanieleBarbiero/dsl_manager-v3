# Formati, copertura e limiti del rilascio

La copertura sotto distingue parser disponibile e prova eseguita. Gli esiti reali sono nei report della consegna; la disponibilità di un backend non implica che ogni documento del formato sia leggibile.

Aggiornamento 2026-09-29: per il core corrente fanno fede [acceptance Windows](../reports/deterministic_core/closure_20260930/acceptance.md) e [registro di copertura](copertura_deterministica.md). La prova PDF/OCR del rilascio 3.0.0 rimane storica; questa modifica non ricertifica tutti i backend Docling.

| Formato | Percorso | Prove eseguite |
|---|---|---|
| SQL, DDL, PLS/PLSQL, PKS/PKB, PRC/FNC/TRG, PCK/TPB/TPS, DML | SQLGlot + scanner procedurale | Dieci dialetti DDL; Oracle package, procedure, trigger, blocchi anonimi; funzioni PostgreSQL, T-SQL e DELIMITER MySQL; UTF-16, CTE, subquery, legacy e SQL dinamico |
| Java Oracle nei file SQL (`CREATE JAVA SOURCE/CLASS/RESOURCE`, call specification `LANGUAGE JAVA NAME`), sorgenti Java senza envelope e file `.java` | tree-sitter-java, solo con `java_analysis=on` ed extra `java` | Fixture sintetiche: envelope, call spec standalone/package/type, file misti, unità esterne, sorgenti headless, Unicode, CRLF, nomi con `/`, overload, classi annidate/anonime/locali, interface/enum/record; differenziale opzionale su corpus Oracle locale non distribuito |
| XLSX/XLSM | Preflight/manifest OOXML v1 + Docling sugli stessi byte | Golden esatto, formule/cache, fogli hidden/very_hidden, link, hash macro; XLSX Vega convertito realmente |
| XLS | xlrd | Workbook binario reale con testo e numero, attraverso worker |
| ODS | odfpy | Documento reale con formula; rifiuto del superamento budget, senza troncamento |
| XLSB | pyxlsb | Backend integrato; manca una fixture binaria reale di accettazione |
| DOCX | Docling + preflight metadata OOXML | Manuale Vega reale; conversione e round-trip completo |
| PDF | Docling, OCR/layout/tabelle | Fixture PDF reale, modelli scaricati e conversione verificata |
| PPTX, HTML/HTM | Docling | Fixture reali passate attraverso il worker |
| Forms XML / XML generico | lxml senza DTD/entity/rete | Forms Vega, item/field/button/operation, namespace e XML ostile |
| LOG | Testo strutturato o JSON per riga | Cinque eventi Vega; identità di occorrenza e assenza di falsi conflitti |
| CSV/TSV, JSON/JSONL/NDJSON, YAML/YML | Parser strutturali | Worker reale, delimitatori e timestamp YAML preservati come testo |
| EML/MHTML/MHT | Parser MIME; estrazione text/plain e text/html | Fixture reali, intestazioni e contenuto; gli allegati non vengono acquisiti automaticamente |
| TXT/MD/MARKDOWN/RST/INI/CFG/PROPERTIES | Decodifica e chunk con offset | Testo reale, accenti, segnali temporali e selezione AI |
| PNG/JPEG/TIFF/BMP/WEBP, ASCIIDOC/ADOC, VTT, TEX, EPUB, MSG | Backend Docling | Instradamento presente; non certificati con fixture dedicate in questo rilascio |

## SQL

Il catalogo SQLGlot installato fornisce 33 dialetti nominati, oltre al generico. I casi DDL dedicati coprono Oracle, PostgreSQL, MySQL, T-SQL, SQLite, BigQuery, Snowflake, DuckDB, Spark e Teradata. DB2, Firebird, Informix e Sybase hanno riconoscimento lessicale: l'eventuale AST generico è usato soltanto quando accettato, con diagnostica esplicita.

Il motore non esegue SQL e non è un compilatore completo di ogni linguaggio procedurale. Le unità sono conservate, con dipendenze statiche dove risolvibili. SQL dinamico rimane irrisolto. Le operazioni ALTER/DROP sono riconosciute, ma non si simula un catalogo completo risultante dall'esecuzione di tutte le migrazioni. Le dipendenze di membri package possono essere attribuite al contenitore. Non si promette risoluzione universale di overload, macro, variabili o SQL generato.

Il subset deterministico v4 include PK/FK/UNIQUE/CHECK, default, nullability, indici e ALTER ADD CONSTRAINT; UPDATE, INSERT con colonne esplicite, DELETE, MERGE per ramo, SELECT e CALL/EXEC statici. Literal string/number/boolean/null sono tipizzati; i numeri mantengono la rappresentazione decimale. Parametri, bind ed espressioni AST rimangono distinti. INSERT senza colonne, tuple assignment, arità non determinabili, risoluzioni ambigue e SQL dinamico producono copertura parziale esplicita. Un insieme ammesso da CHECK e un limite numerico sono regole dichiarate; transizioni di stato, valuta, unità e intenzioni operative non vengono inferite.

Una sintassi comune non identifica una versione. Una dichiarazione esplicita o marcatori legacy vengono riportati come evidenza, con l'override disponibile; non sono una certificazione del DBMS reale.

## Java Oracle (opzionale)

L'analisi Java è disattivata per default (`java_analysis=off`): con il flag spento i moduli Java non vengono importati, le evidenze, la cache e il digest di configurazione restano quelli del rilascio precedente e i file `.java` restano `unsupported_format`. Con `java_analysis=on`, i file SQL che contengono unità Java Oracle isolano la regione Java (fino alla prima riga contenente solo `/`, anche con CRLF, oppure al successivo `CREATE` di un oggetto SQL a inizio riga fuori da commenti e stringhe Java; le unità esterne terminano al `;`) invece di produrre `sql_unparsed`; il resto del file segue il percorso SQL invariato. I file SQL senza unità Java mantengono parse e cache. Serve l'extra `java` (`pip install ".[java]"`): senza grammatica il parse SQL resta quello legacy, con l'avviso `java_parser_unavailable`.

Il parser Java non compila, non usa classpath e non inferisce tipi. Emette classi, interfacce, enum, record, metodi e costruttori con firma per tipi, e dipendenze soltanto quando il bersaglio è lessicalmente certo: stessa classe o classe contenitore, qualificatore statico di tipo noto, import singolo o statico. Le chiamate su ricevitori non tipizzabili sono conteggiate in `java_receiver_type_unresolved`; le chiamate certe verso la piattaforma (`java.*`, `javax.*`, le classi `java.lang` più comuni e i metodi di `Object`) sono contate nei metadati `java_platform_calls` e non diventano relazioni. Le call specification collegano procedure, funzioni, membri di package e di type Oracle al metodo Java nominato, con firma e tipo di ritorno.

Limiti dichiarati:

- una riga contenente solo `/` termina l'unità anche dentro un commento Java, come in SQL*Plus: il resto diventa `java_unparsed`/`sql_unparsed` con stato `partial`;
- i nomi di classi annidate usano il punto (`Outer.Inner`); il `$` resta nelle classi anonime e locali (`Outer$1`, `Outer$1Helper`), numerate per ordine di apparizione nel file come approssimazione di javac;
- la risoluzione Java è esatta e sensibile alle maiuscole: nessun suffisso, nessun casefold, nessuna scelta per arità tra overload (restano `ambiguous`);
- gli import on-demand (`import a.b.*`) e l'ereditarietà non sono usati per risolvere chiamate; le classi importate assenti dal workspace restano `target_absent`;
- i nomi `NAMED` non quotati vengono portati in maiuscolo come fa Oracle; i nomi con `/` sono convertiti al nome binario con il punto e il nome dichiarato resta in `declared_name`;
- unità `JAVA CLASS/RESOURCE USING BFILE|BLOB|CLOB` sono dichiarate ma il binario non viene analizzato (`java_binary_not_analyzed`); senza `NAMED` la componente è `unsupported`;
- i membri di una type specification con call spec Java non diventano funzioni SQL (comportamento legacy invariato).


Per OOXML vengono mantenuti valori, formule e cache separati. Non si ricalcolano formule e non si eseguono macro o link esterni. XLS e XLSB conservano i valori leggibili dai backend, ma non garantiscono il medesimo manifest strutturale di XLSX/XLSM. ODS conserva le formule disponibili. La copertura di metadati proprietari, oggetti incorporati e formattazione non è universale.

Il risultato di estrazione dipende dal documento: OCR, PDF scansiti e layout complessi richiedono verifica umana. La conversione PDF provata non certifica tutte le lingue OCR o tutti i tipi di scansione. Documenti cifrati, corrotti, con estensioni sconosciute o oltre budget danno errori visibili e conservano i byte acquisiti.

## Temporalità e governance

Precisione fino al microsecondo; maggiore precisione viene rifiutata per evitare troncamenti. Timestamp naive non confermabili; nessuna conversione automatica di metadata operativi in validità semantica. La propagazione è esplicita e non si ricalcola continuamente dopo modifiche alle premesse.

La provenance valida una citazione e il suo riferimento, non la verità di un'inferenza. Mapping, conflict e question AI restano candidati senza promozione automatica. Le prove AI sono fixture dichiarate, non risultati di chiamate a un modello esterno.

## Compatibilità e piattaforme

Python richiesto: 3.12 x64. L'acceptance corrente registra Windows nativo e PowerShell 5.1, inclusi spazi, accenti, BOM, UTF-16, riavvio, cache e migrazione SQLite 2→3. Le prove Linux x86-64 precedenti rimangono storiche. Gli ID e gli schemi runtime M3 sono nuovi rispetto a v1. Non viene migrato automaticamente il registro di review v1: conservare il workspace v1 e reimportare il corpus in M3.

La UI è un'applicazione locale, con una coda di job. Non è un servizio distribuito o multiutente. Può registrare più workspace indipendenti ma un singolo processo server ne usa uno solo come attivo in ogni momento; lo switch non sostituisce locking multi-processo e viene bloccato durante job queued/running. Il registry dei workspace contiene percorsi locali, non dati DSL. I limiti sono configurabili entro massimi espliciti; non sono stati eseguiti benchmark su corpus molto grandi. I test eseguiti dimostrano gli scenari dichiarati, non l'assenza universale di bug.
