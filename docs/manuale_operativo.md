# Manuale operativo DSLM3

## 1. Installazione e workspace

Usare Python 3.12 a 64 bit. Eseguire `installa.cmd` e poi `avvia.cmd` su Windows, oppure `bash installa.sh` e `bash avvia.sh` su Linux. Gli script installano PyTorch CPU e il pacchetto; l'applicazione ascolta soltanto su `127.0.0.1:8765`.

Il workspace predefinito è la cartella `workspace` accanto agli script. Contiene `project.json`, database `registry.sqlite3`, corpus, copie immutabili, artefatti, pacchetti AI e log. Conservare **l'intero workspace** per mantenere revisioni, decisioni e provenienza. Per copiarlo a freddo, arrestare il server; con SQLite attivo non copiare soltanto il file `.sqlite3`, perché possono esistere file WAL associati.

Le dipendenze richiedono Internet durante l'installazione. PDF e immagini possono scaricare modelli alla prima conversione. I normali file del corpus sono elaborati localmente; l'app non avvia richieste a modelli AI esterni. Un cambio di macchina può richiedere nuovi download dei modelli. I log rendono visibili problemi di rete o memoria del worker.

## 2. Il primo percorso: Vega

1. In **Panoramica**, premere **Carica il laboratorio**: vengono acquisite sei fonti con gli stessi byte della baseline.
2. In **Impostazioni e attività**, impostare un identificativo stabile del revisore. Il default `local-user` può essere sostituito con il proprio nome operativo.
3. Scegliere **Profilo conservativo** se si desidera applicare le policy tecniche nominate. Lasciare **Tutto manuale** per valutare ogni proposta.
4. In Panoramica premere **Elabora il corpus**. L'app esegue parsing, derivazione, policy eventualmente abilitate, merge e riconciliazione. Senza policy, le proposte rimangono pending.
5. In **Fonti ed evidenze**, usare **Esplora** per vedere testo, struttura, localizzatori, stato e diagnostica.
6. In **Proposte e review**, valutare le proposte rimaste in attesa. Eseguire **Merge delle confermate**, quindi **Riconcilia** dopo eventuali revoche o correzioni.
7. Aprire **Conoscenza** e **Output e confronto** per esportare uno snapshot.

Il laboratorio automatizzato `python -m dslm3.lab --workspace ...` aggiunge risposte AI controllate e verifica l'intero round-trip. La sola acquisizione Vega nella UI non inventa un'interpretazione AI: i pacchetti devono essere elaborati esternamente e reimportati, oppure si può eseguire il laboratorio dichiaratamente simulato.

Le fonti sono DDL Oracle, procedura/trigger, Forms XML, cinque eventi log, manuale DOCX e matrice XLSX. Il manuale indica P1 entro **30 minuti**, la matrice **1 ora**: il laboratorio conserva le due affermazioni come conflitto reale. Gli eventi log distinti non diventano falsi conflitti di stato.

## 3. Acquisire il proprio corpus

In **Fonti ed evidenze** si possono caricare file, una cartella dal browser oppure indicare una directory accessibile al processo Python sul PC. La scansione è ricorsiva. Le esclusioni in Impostazioni accettano pattern come `*.tmp` o `archivio/*`.

Per un corpus esterno, ripetere la scansione dalla **stessa directory esterna** per rilevare modifiche e rimozioni. La scansione senza percorso usa la copia interna `workspace/corpus`. Un file escluso già registrato non viene cancellato. Le fonti mancanti conservano storia ed evidenze, ma i loro supporti non sono effettivi. La scansione non cancella i file originali.

Ogni contenuto diverso genera una revisione con SHA-256 e una copia immutabile. Una nuova scansione degli stessi byte riusa la revisione. I percorsi relativi distinguono fonti con nomi identici in cartelle diverse. I link simbolici vengono ignorati. Il limite iniziale per file è 64 MiB; tutti i superamenti producono un errore esplicito.

## 4. Parser e diagnostica

L'app sceglie il parser dall'estensione; SQL usa dichiarazioni, indizi sintattici e un eventuale override in Impostazioni. Il catalogo mostra i dialetti AST e quelli lessicali. Con `auto`, sintassi condivisa significa incertezza dichiarata. La versione non viene inventata.

Un cambio di dialetto e una nuova elaborazione possono produrre evidenze diverse per gli stessi byte. Le interpretazioni precedenti rimangono nel registro ma non sostengono più la conoscenza corrente. Tornare a un'interpretazione già elaborata riattiva la cache con un nuovo record. Una proposta invariata conserva la review quando si aggiungono altre fonti.

`success` indica che il parser ha terminato; leggere comunque gli avvisi. `partial` indica un risultato parziale dichiarato. `error` non produce evidenze consolidate e rimanda al log. SQL non riconosciuto resta testo con diagnostica e non viene trasformato in colonne inventate. Il worker ha timeout, limite di memoria e limite di output; un arresto per risorse è visibile.

Per Excel OOXML la vista strutturale è autorevole per formule, cache, fogli nascosti, named range, tabelle, link e hash VBA. Il testo Docling serve alla lettura e all'AI. Le due viste consumano gli stessi byte. Macro e link non vengono eseguiti; formule e valori memorizzati non sono confusi.

## 5. Review, correzioni e conoscenza

Aprire **Valuta** per leggere proposta e citazione. Le decisioni possibili sono confermare, rifiutare e lasciare in attesa. Una correzione crea una nuova foglia della catena: non riscrive il record originale. La UI controlla la testa della review nelle decisioni individuali per evitare sovrascritture di una decisione cambiata.

**Confermare e consolidare sono operazioni distinte.** Il contatore delle confermate non consolidate indica lavoro ancora da includere nel DSL. Il merge accetta soltanto foglie confermate, su revisioni/fonti/evidenze correnti. Il merge `strict` rifiuta atomicamente un batch con candidati non eleggibili.

Uno stesso fatto può avere più supporti. Revocarne uno non cancella gli altri; l'oggetto rimane effettivo finché ha almeno un supporto valido. Dopo correzioni o revoche eseguire **Riconcilia**: gli export normali bloccano le riconciliazioni ancora aperte.

Mapping, question e conflict importati dall'AI rimangono candidati consultabili: non diventano automaticamente fatti o relazioni. I conflitti fra fatti incompatibili sono calcolati sulla conoscenza effettiva, tenendo conto degli intervalli disponibili.

## 6. Pacchetti AI

In **Interpretazione AI** sono disponibili due route:

| Route | Scopo |
|---|---|
| `technical_extraction` | Strutture tecniche non già coperte da proposte confermate |
| `domain_interpretation` | Regole e concetti con manuali, tabelle e contesto tecnico |

Il piano conserva rango, coverage, motivi di inclusione/esclusione e budget. **Motivi** permette di capire perché un'evidenza è stata scelta. **Prepara entrambe le route** crea tutti i pacchetti non vuoti. Selezionarli e scaricarli; ogni package contiene istruzioni, contenuto, manifest, schema JSONL e template da compilare.

Gli archivi ZIP prodotti dall'app per l'handoff AI sono una funzione applicativa; il salvataggio del progetto su Drive è invece per singoli file. Nessun ZIP è usato come memoria di lavoro della consegna.

Il modello esterno deve restituire una riga JSON per candidato, con `candidate_id` univoco nel file, ID di revisione/evidenza e citazione letterale non vuota. Il template contiene segnaposto che devono essere sostituiti. Le citazioni false, le evidenze fuori package e i batch malformati sono rifiutati senza importazioni parziali. Gli intervalli temporali richiedono il flusso dedicato.

Importare ogni risposta sotto il package giusto; ID esterni uguali in package diversi restano distinti. Le risposte entrano come pending. Il percorso termina con **review → merge → snapshot**. Una revisione o interpretazione cambiata rende il package obsoleto. La CLI consente `--allow-stale` per conservare una risposta storica, ma i supporti obsoleti non diventano effettivi.

## 7. Temporalità

**Estrai segnali temporali** raccoglie dichiarazioni e metadata, nome file, proprietà OOXML, timestamp ZIP, PDF, HTML/JSON-LD e prima acquisizione. Questi segnali mantengono natura, affidabilità, precisione e timezone. Non vengono promossi automaticamente a validità di dominio.

**Confronta e proponi intervalli** raggruppa valori concordi, copie correlate e conflitti; ogni intervallo resta pending. Un anno o mese viene rappresentato come envelope inclusivo; timestamp senza timezone non possono essere confermati finché non vengono corretti con un offset o una zona risolta. Le ore locali ambigue per il cambio dell'ora sono rifiutate.

La propagazione richiede soggetti origine nel formato `tipo:ID`, destinazione e policy: `explicit_copy`, `intersection`, `aggregation` oppure `conflict`. Le proposte vanno nuovamente valutate. L'aggregazione conserva gli intervalli disgiunti. La propagazione è un'operazione esplicita una tantum, non un'inferenza continuamente ricalcolata dopo una revoca della premessa.

## 8. Output

Lo snapshot **profilo 2** contiene la conoscenza effettiva e gli intervalli. Il **profilo 1** è una vista fisica storica, pensata per confronto con il comportamento legacy: può includere oggetti materializzati che non sono più effettivi. Non è una migrazione byte-per-byte del formato o degli ID v1.

Scaricare JSON, YAML o Markdown dalla UI. Il diff separa cambiamenti strutturali, di governance e temporali, con supporti prima/dopo. Un confronto tra profili diversi richiede l'opzione esplicita.

Il grafo GEXF 1.3 include entità, fatti, fonti, conflitti e archi con provenienza. Per i grafi dinamici sono disponibili `strict`, `omit` e `separate`; quest'ultima separa data e timestamp. Le risorse XSD sono locali e controllate tramite hash. Gli intervalli degli archi devono rispettare quelli degli estremi.

## 9. CLI e API

```text
python -m dslm3 -w workspace status
python -m dslm3 -w workspace scan "C:\dati\corpus"
python -m dslm3 -w workspace profile conservative
python -m dslm3 -w workspace pipeline
python -m dslm3 -w workspace package-all
python -m dslm3 -w workspace ai-import AIPKG_ID risposta.jsonl
python -m dslm3 -w workspace review CAND_ID --outcome confirmed
python -m dslm3 -w workspace merge
python -m dslm3 -w workspace reconcile
python -m dslm3 -w workspace snapshot
```

Usare l'interprete `.venv` installato. `--workspace` precede il comando. `action OPERAZIONE --args-file richiesta.json` espone tutte le operazioni del servizio con JSON senza problemi di escaping della shell. `--help` elenca le opzioni; gli exit code sono 0 successo, 2 errore, 6 parziale.

La documentazione API è disponibile su `/api/docs`. Le scritture richiedono il token di sessione fornito da `/api/bootstrap` e sono limitate all'origine locale. Il servizio non è progettato come server multiutente esposto in rete.

## 10. Problemi comuni

- **Porta occupata:** avviare con `avvia.cmd --port 8766` oppure il parametro `--port` sulla CLI.
- **Download modelli fallito:** controllare rete/proxy nel log del worker, correggere l'ambiente e ripetere `parse --retry`. Non viene simulata la conversione.
- **Confermata ma assente nel DSL:** eseguire merge, controllare fonte/revisione/interpretazione corrente e poi reconcile.
- **Package obsoleto:** ricalcolare il piano e generare il package sulle evidenze correnti.
- **Errore dopo cambio file:** vedere Fonte → Esplora → Report parser e Impostazioni → Registro delle operazioni.

Non aprire lo stesso workspace contemporaneamente con processi UI/CLI che eseguono acquisizioni o configurazioni: la UI serializza i job, mentre i file del corpus/configurazione non hanno un lock globale tra processi. Le review SQLite mantengono i propri controlli transazionali.
