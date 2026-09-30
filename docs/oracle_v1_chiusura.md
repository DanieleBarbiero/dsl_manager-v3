# G15 — verifica dell'oracle informativo v1, 30 settembre 2026

Requisito riesaminato: §13 del prompt v1.3. V1 è un oracle delle informazioni
strutturali, non lo schema da replicare. Il confronto legge esclusivamente il
commit `8b576eb605b2509ebe84785aae6b2d1e94046b8b` attraverso Git; non legge le
modifiche locali del checkout v1. Gli import comprendono le dipendenze originali
del modulo, estratte in una directory temporanea esterna al repository.
`oracle_v1_inventory.json` identifica con SHA-256 tutti i sorgenti esaminati.

La prova corrente è in
`reports/deterministic_core/closure_20260930/acceptance.json`, gate G15;
`details/G15-*.json` contiene attesi e osservazioni delle nuove prove realmente
eseguite. Un file golden v3 da solo non soddisfa questo gate.

| Sorgente / invariante pertinente | Trattamento e prova verificabile |
|---|---|
| `schema_resolution.py`: tabelle, colonne, unità, target assente, basi | Confronto diretto `test_pinned_v1_schema_resolution_information`: stati e target comuni; dichiarazioni usate come basi. V3 conserva anche segmenti quoted, alternative e fingerprint (test degli overload e COV-03). |
| `schema_resolution.py`: colonna inesistente in tabella nota | V1 la chiama inconsistent. V3 mantiene il componente unresolved, ma ora distingue `column_absent_from_schema` da `target_absent`, conserva la tabella risolta nei prerequisiti e le sue evidence. Il test confronta esplicitamente i due significati, senza equiparare i nomi degli stati. |
| `candidate_derivation.py`: tipi, regole, locator, ordinamento, deduplica, FK | Esecuzione diretta di `derive_rule_records` in `test_pinned_v1_candidate_derivation_slice21`; candidati v3 reali, retry, pending e nessun oggetto prima della review. Per FK la relazione v1 references corrisponde alla specifica foreign_key v3, mantenendo gli attributi ordinati. |
| `test_slice_21_deterministic_derivation.py`: FK risolta/non risolta | Confronto diretto nel test slice21; v3 conserva la dichiarazione anche quando la relazione non è risolvibile. COV-01–06 verificano arità, ambiguità, modifica/rimozione/ripristino dei target e storico. |
| Slice21: XML read/write espliciti, menzione ambigua | `test_forms_resolution_modes_and_namespace`, oracle Forms preesistente e test slice32 dei blocchi: mapping non implica writes_to, modalità esplicite e contraddizioni sono distinte. Questa rappresentazione v3 separa le informazioni che v1 mescolava. |
| Slice21: funzione/procedura e dipendenze | Oracle DB preesistente più `test_pinned_v1_slice32_scope_and_event_information`; chiamate, parametri, subquery correlate, letture e scritture. G05 aggiunge pseudorecord risolti rispetto alla tabella del trigger. |
| Slice21: locator obbligatorio e segnaposto rifiutati | L'oracle prova il rifiuto del locator incompleto; `test_provenance_atomic_batch` verifica in v3 citazioni inventate, batch atomici e REPLACE_VALUE. V3 conserva locator ed evidence immutabili, evitando la duplicazione nominale di tutte le chiavi del locator v1. |
| Slice21: run, batch, CLI e ID amministrativi | Non applicabile l'uguaglianza di ID, payload hash e numero di batch tra versioni: §13 esclude la replica della persistenza/CLI. Applicabile e provata invece l'idempotenza semantica, l'origine deterministica, lo stato pending e l'assenza di materializzazione senza review. |
| `test_slice_25_excel_candidates.py`: workbook, sheet, region, named range, table, reference | `test_pinned_v1_slice25_excel_candidates` esegue tutti i sei producer v1 sul workbook originale pinned, verificato contro il checksum v1. Confronta il manifest v1 effettivo con quello v3 e le candidate strutturali dei due deriver, non solo un golden. |
| Slice25: visibilità, formule/cache, regioni identiche, nomi locali, attributi e locator | Manifest completi identici, celle e coordinate nelle definition v3, named range distinti per workbook/scope/foglio; il test verifica due LocalBlock (scope workbook e scope sheet). Relazioni OPC e metadati del package restano nel manifest persistito. La correzione minima delle identità evita false collisioni tra nomi uguali in scope distinti. |
| Slice25: riferimenti interni named_range/region/table | V1 materializza una proiezione regex della formula. V3 conserva la formula completa nelle celle delle regioni e tutte le dichiarazioni/scoping nel manifest e nelle definition. Il confronto esegue la proiezione v1, verifica tutti e tre i tipi di riferimento e ritrova ogni formula/coordinate nelle candidate v3; nessuna informazione della formula o dei target viene eliminata per eguagliare il vecchio grafo. V3 non promette archi interni references identici a v1. |
| Slice25: link esterni, macro, Docling e governance | Rete vietata nel confronto; link non dereferenziati, manifest formula/cache autorevole, Docling reale. Test macro e formati preesistenti; named policy e pending separati da coverage in G12/COV-07. Gli ID delle policy v1 non sono un contratto v3. Nessuna autorizzazione a promuovere automaticamente interpretazioni del workbook. |
| `test_slice_32_semantic_integrity.py`: eventi distinti, retry, provenance | Confronto diretto delle quattro occorrenze, incluse due processed, nei producer v1/v3. V3 conserva il record completo in occurrence e la relazione observed_on; `test_log_json_identical_occurrences_retry_and_no_conflict` esercita review/merge e assenza di falsi conflitti. |
| Slice32: conflitti monovalore, alias multivalore | `test_pinned_v1_slice32_multivalue_representation` legge il catalogo v1 e prova la rappresentazione v3: due valori status producono un conflitto, due relazioni has_alias coesistono. Non si clonano le eccezioni nominali del catalogo v1; non è una migrazione automatica di fact legacy entity_alias. Gli eventi sono soggetti distinti, non valori in conflitto del componente. |
| Slice32: scope SQL, pseudorecord, barriera auto-review | Confronto diretto scope SQL e prova G05. V1 parser conserva NEW.A/OLD.A ma il deriver v2 li scarta; v3 li associa alla tabella del trigger. V1 può emettere candidate unresolved non auto-confermabili; v3 conserva il blocco nella coverage e non emette una relazione senza endpoint verificato: COV-01/03/07 e `test_ai_cannot_autoapprove_and_strict_atomic`. |
| Slice32: item omonimi in blocchi distinti e operazioni pulsanti | Oracle XML condiviso, `test_forms_items_keep_block_identity_and_button_operation_can_auto_review` e `test_forms_resolution_modes_and_namespace`: identità F.B.ITEM, attributi, xpath, mapping/calls e target mancanti o incompatibili. V3 registra distintamente uses_table, maps_to e modalità esplicite. |
| Slice11 / chunking | Oracle diretto preesistente: heading conservati; v3 ricostruisce tutti i caratteri. Prova documentata del newline perso da v1. |
| Slice12 / DDL | Oracle diretto preesistente: datatype, nullability, default, constraint, PK/FK e index; v3 aggiunge AST interrogabili. |
| Slice13 / Forms | Oracle XML diretto e prove sopra; nessuna inferenza maps_to → writes_to. |
| Slice14 / DB code e log | Oracle DB diretto, nuovo confronto scope/eventi slice32 e test di occorrenze/provenance. CLI e tabelle di registry legacy non sono riprodotte. |

## Eccezioni dimostrate, non normalizzazioni per nascondere perdite

Il producer FK v1 usa `_text_list`, che ordina separatamente le liste: la
fixture con `(B,A) REFERENCES P(Y,X)` diventa `(A,B)/(X,Y)`. Il test asserisce
espressamente questo difetto dell'oracle e richiede che v3 conservi `(B,A)/(Y,X)`.
Non si ordina l'output v3 per far passare una falsa uguaglianza.

Il chunker v1 perde un separatore newline nella fixture condivisa; v3 lo conserva.
L'inferenza Forms di scrittura dal solo mapping non è riprodotta. I riferimenti
pseudorecord scartati dal deriver v1 diventano dipendenze verificate in v3.
Le strutture SQL tipizzate e i record evento/Excel completi non vengono ridotti
ai vecchi fact nominali. Gli ID raw e i contatori amministrativi tra versioni
non sono confrontati come se fossero equivalenti.

XLSB, backend senza fixture, migrazione di workspace v1 e CLI legacy rimangono
fuori dalla certificazione. Questi limiti non sono conversioni di failure in pass.
