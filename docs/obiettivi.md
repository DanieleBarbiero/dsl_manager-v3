# DSLM3 — obiettivi, gate e protocollo anti-drift

## Pass corrente — chiusura core deterministico, 2026-09-30

Branch locale `feat/deterministic-core-upgrade`, baseline
`a7117e061b393123e3b7b2ec22bf171687756447`, padre `fix/vega-quality-backlog`.
Nessun nuovo branch, push o aggiornamento remoto. Le sezioni del rilascio 3.0.0
qui sotto documentano la storia; non attestano questa modifica.

Contratto e registro: [contratto v4](contratto_deterministico.md),
[copertura per componente](copertura_deterministica.md).
G01–G18, COV-01–08 e BIZ-01–08 sono tracciati con test e attesi nel
[rapporto eseguibile](../reports/deterministic_core/closure_20260930/acceptance.json).
Chiusura verificata: **G01–G18, COV-01–08 e BIZ-01–08 passed**, 153 test
passati, zero falliti/saltati; Vega 12/12 e 19/19, browser e wheel passati.
Il commit iniziale del pass è
`53bf0c31638199c26fb86c1523018680bf9c34c1`; la baseline originaria resta distinta.
Il collaudo con 136 test del 29 settembre è storico e non certifica questo pass.
Il [rapporto corrente](rapporto_core_deterministico.md) delimita il subset e
i limiti. Il manifest 3.0.0 rimane storico e non certifica gli hash modificati.

Stato iniziale: 17 settembre 2026. Richiesta: riscrittura di DSL Manager v1 con UI web locale centrale; GitHub solo lettura; tutti i deliverable in `gdrive/projects/dslm3`.
Baseline: `DanieleBarbiero/dsl_manager-v1`, commit `c443b6a457b78229517a481fc5850dc8b44ecc3a`, applicazione 1.1.0, 77 file / 40.092 righe Python. Allegato: `dslm1+vega.md`.

## Regola operativa

Uno step è chiuso solo dopo esecuzione del relativo controllo e salvataggio dell'evidenza. Un errore riapre lo step; un fallback deve essere visibile. Le funzioni non implementate non possono essere dichiarate complete. Ogni checkpoint aggiorna questo file e il diario. Nessuna scrittura, commit, issue, PR o push su GitHub.

## Stato conclusivo — rilascio 3.0.0

**Consegna conclusa.** Sorgenti ricostruiti, 79 test superati, Vega 19/19, browser Chromium desktop/mobile, PDF Docling reale e wheel installato fuori dai sorgenti verificati. Documentazione e istruzioni riproducibili completate. I singoli file sono salvati su Drive; il controllo remoto dei 141 file di contenuto ha verificato nome e dimensione e la corrispondenza con gli hash registrati al salvataggio. Report di verifica e manifest finale completano la consegna.

Le prove correnti sono identificate in `rapporto_finale.md`; `reports/precedente` e il vecchio ZIP sono soltanto storici. Limiti: `formati_e_limiti.md`, inclusi Windows non eseguito e copertura SQL non universale.

## Step

- [x] 01 — Baseline e ambiente: inventario v1, lettura rapporto, installazione dipendenze reali, smoke test Docling (conversione, non solo import).
- [x] 02 — Contratti: matrice di parità completa, architettura semplificata, formato persistente e criteri Vega.
- [x] 03 — Acquisizione e parser: revisioni immutabili; SQL multi-dialetto con AST e limiti dichiarati; Oracle PL/SQL; Forms; log; documenti; Excel fedele ai byte.
- [x] 04 — Conoscenza governata: candidati, validazione provenance, review append-only, correzioni, merge, supporti multipli, reconcile, conflitti reali.
- [x] 05 — Temporalità: segnali grezzi separati dalla validità; precisione/timezone/concordanza; proposte pending; propagazione esplicita e supporti multipli.
- [x] 06 — AI e output: selezione spiegabile, budget, package multipli, JSONL con citazioni verificabili, round-trip fino al merge, DSL JSON/YAML/Markdown, diff, GEXF statico/dinamico.
- [x] 07 — UI web: mini server localhost, flusso interattivo completo, stato leggibile, errori e motivi, visualizzazione evidenze/review/temporalità/export; CLI fallback.
- [x] 08 — Vega M3 e collaudo: sei fonti originali più casi estesi, regressioni dei difetti allegati, test negativi e reali, browser, riavvio/idempotenza, packaging e manuale Windows.

## Vincoli che non si possono semplificare via

1. Byte sorgente → revisione → evidenza localizzata → candidato → review → conoscenza consolidata.
2. Parser, Docling, nomi file e AI non approvano conoscenza autonomamente.
3. I segnali temporali operativi/documentali non equivalgono alla validità di dominio.
4. Formule e valori memorizzati Excel sono distinti; macro e link esterni non vengono eseguiti.
5. SQL ambiguo o non supportato produce diagnostica; non produce colonne inventate.
6. Il rientro AI deve arrivare a review e merge espliciti, con tutti i package selezionati.
7. Eventi successivi non costituiscono automaticamente conflitti di stato.
8. Nessuna promessa di riconoscere con certezza ogni dialetto/versione: catalogo reale, override esplicito, diagnostica dell'incertezza e test dei dialetti dichiarati.
9. Vietato dichiarare assenza universale di bug: il report finale deve distinguere test eseguiti e limiti residui.

## Step 09 — chiarezza workflow UI e workspace multipli (modifica 2026-09-18)

Stato iniziale storico: patch preparata, gate da rieseguire. Il 29 settembre i
controlli seguenti sono stati verificati nuovamente nella suite/browser/Vega
dell'acceptance core; le prove 3.0.0 rimangono storiche.

- [x] UI: percorso `00 → 01 → 02 → 03 → 02 → 04 → 02 → 05 → 06`, con 02 come gate ricorrente e pipeline rapida come scorciatoia.
- [x] Workspace: registry locale, create/register/switch/forget, isolamento e switch bloccato durante job attivi.
- [x] Regressioni: `tests/test_workspaces.py`, `tests/test_web.py`, suite completa del 29 settembre: 136 passed (prova storica).
- [x] Browser: navigazione e selettore workspace in Chromium desktop/mobile.
- [x] Vega integrato: nuovo workspace, 19/19; prova deterministica separata 12/12.
- [x] Documentazione: README, manuale, architettura, limiti, diario, protocollo e START_HERE allineati.
- [x] Consegna locale: rapporto corrente, patch binaria completa e manifest storico contrassegnato come non rigenerato/non certificante i file correnti, come consentito dall'incarico. Nessuna pubblicazione di release.
