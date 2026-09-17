# Formati, copertura e limiti del rilascio

La copertura sotto distingue parser disponibile e prova eseguita. Gli esiti reali sono nei report della consegna; la disponibilità di un backend non implica che ogni documento del formato sia leggibile.

| Formato | Percorso | Prove eseguite |
|---|---|---|
| SQL, DDL, PLS/PLSQL, PKS/PKB, PRC/FNC/TRG, PCK/TPB/TPS, DML | SQLGlot + scanner procedurale | Dieci dialetti DDL; Oracle package, procedure, trigger, blocchi anonimi; funzioni PostgreSQL, T-SQL e DELIMITER MySQL; UTF-16, CTE, subquery, legacy e SQL dinamico |
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

Una sintassi comune non identifica una versione. Una dichiarazione esplicita o marcatori legacy vengono riportati come evidenza, con l'override disponibile; non sono una certificazione del DBMS reale.

## Excel e documenti

Per OOXML vengono mantenuti valori, formule e cache separati. Non si ricalcolano formule e non si eseguono macro o link esterni. XLS e XLSB conservano i valori leggibili dai backend, ma non garantiscono il medesimo manifest strutturale di XLSX/XLSM. ODS conserva le formule disponibili. La copertura di metadati proprietari, oggetti incorporati e formattazione non è universale.

Il risultato di estrazione dipende dal documento: OCR, PDF scansiti e layout complessi richiedono verifica umana. La conversione PDF provata non certifica tutte le lingue OCR o tutti i tipi di scansione. Documenti cifrati, corrotti, con estensioni sconosciute o oltre budget danno errori visibili e conservano i byte acquisiti.

## Temporalità e governance

Precisione fino al microsecondo; maggiore precisione viene rifiutata per evitare troncamenti. Timestamp naive non confermabili; nessuna conversione automatica di metadata operativi in validità semantica. La propagazione è esplicita e non si ricalcola continuamente dopo modifiche alle premesse.

La provenance valida una citazione e il suo riferimento, non la verità di un'inferenza. Mapping, conflict e question AI restano candidati senza promozione automatica. Le prove AI sono fixture dichiarate, non risultati di chiamate a un modello esterno.

## Compatibilità e piattaforme

Python richiesto: 3.12. L'ambiente eseguito è Linux x86-64; Windows ha istruzioni e launcher dedicati ma non è stato eseguito in questa sessione. Gli ID e gli schemi runtime M3 sono nuovi. Non viene migrato automaticamente il registro di review v1: conservare il workspace v1 e reimportare il corpus in M3.

La UI è un'applicazione locale, con una coda di job. Non è un servizio distribuito o multiutente. I limiti sono configurabili entro massimi espliciti; non sono stati eseguiti benchmark su corpus molto grandi. I test eseguiti dimostrano gli scenari dichiarati, non l'assenza universale di bug.
