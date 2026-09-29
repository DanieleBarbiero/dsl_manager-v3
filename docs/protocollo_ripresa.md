# DSLM3 — protocollo di ripresa corrente

Questo documento è il riferimento operativo per riprendere il lavoro dopo un'interruzione. `docs/protocollo_ripresa_precedente.md` descrive una disconnessione storica e non deve essere aggiornato per lo stato corrente.

## Ordine di bootstrap

1. Leggere `START_HERE.md`.
2. Leggere l'ultima sezione di `docs/diario_tecnico.md`.
3. Cercare in `docs/obiettivi.md` gli step ancora aperti.
4. Leggere questo documento e individuare l'ultimo gate realmente verificato.
5. Leggere `release_manifest.json`: se dichiara una modifica pending/unverified, i suoi hash storici non provano lo stato modificato.
6. Non usare report precedenti come prova della versione corrente dopo una modifica ai sorgenti.

## Stato minimo da salvare durante una modifica

Aggiornare insieme, nello stesso checkpoint logico:

- file sorgente/test modificati;
- `docs/diario_tecnico.md`: cosa è stato fatto e quali comandi sono stati realmente eseguiti;
- `docs/obiettivi.md`: gate aperti/chiusi;
- questo `docs/protocollo_ripresa.md`: prossimo comando/passo sicuro se il lavoro resta incompleto;
- eventuali report nuovi prodotti dai test correnti.

Non creare ZIP come memoria di progetto. Conservare i singoli file. Un gate fallito rimane aperto.

## Ripresa della modifica workflow UI / workspace multipli

Questa sezione è storica rispetto all'incarico core del 29 settembre. Le prove
workflow/workspace sono comprese nella suite e nel browser dell'acceptance corrente.
Per riprodurre autonomamente la vecchia modifica:

1. Verificare che `src/dslm3/workspaces.py` e `tests/test_workspaces.py` esistano.
2. Eseguire almeno:
   - `python -m pytest -q tests/test_workspaces.py tests/test_web.py`
   - `python -m pytest -q`
3. Eseguire il browser check in un workspace nuovo.
4. Eseguire Vega M3 in un workspace nuovo.
5. Correggere ogni regressione prima di aggiornare le prove/documenti come concluse.
6. Solo dopo tutti i gate: decidere il version bump, aggiornare il rapporto di rilascio e rigenerare integralmente `release_manifest.json`.

## Ripresa del core deterministico

Checkpoint concluso: G01–G18 e COV/BIZ passed; 136 test, Vega deterministico 12/12,
integrato 19/19, browser e wheel passati. Non resta implementazione obbligatoria
aperta per questo incarico. Per un'ulteriore modifica ripartire dal rapporto e
rieseguire i controlli pertinenti; i risultati correnti non certificano codice futuro.

Restare su `feat/deterministic-core-upgrade`, HEAD di partenza
`a7117e061b393123e3b7b2ec22bf171687756447`. Non creare altri branch né scrivere
su remoti. Il checkout v1 contiene lavoro esterno all'incarico: non modificarlo.

1. Leggere `docs/rapporto_core_deterministico.md` e
   `reports/deterministic_core/final/acceptance.json`. In un report intermedio
   l'assenza di `status` finale o un gate `not_run` significa esecuzione incompleta.
2. Usare solo Python 3.12 x64 del progetto. I comandi nativi PowerShell 5.1 sono
   in `docs/verifica_core_windows.md`; il wrapper conserva gli exit code.
3. Per una nuova verifica scegliere una directory report distinta e un runtime
   nuovo. Non sovrascrivere una prova conclusa mentre la si usa come evidenza.
4. In caso di errore leggere il log del comando e il JUnit, correggere e ripetere
   i controlli pertinenti. La chiusura richiede G01–G18 e COV/BIZ passed sullo
   stesso snapshot dei sorgenti; uno stato dirty è atteso e viene hashato.
5. Il manifest 3.0.0 rimane storico, esplicitamente non rigenerato per questi file.
   Patch locale in `reports/deterministic_core/change.patch`, con nuovi file e
   output Git binario; nessun database runtime o ambiente virtuale nella consegna.

## Workspace e interruzioni

Ogni workspace è autosufficiente. Per copiarlo a freddo arrestare DSLM3 e copiare l'intera directory, non soltanto `registry.sqlite3`. Il file `.dslm3-workspaces.json` è solo un indice locale dei percorsi e può essere ricostruito registrando nuovamente i workspace esistenti.

Per un test pulito, creare preferibilmente un workspace nuovo. Per azzerare quello predefinito: arrestare il server, eliminare il contenuto della directory `workspace`, riavviare e ricaricare Vega. Non cancellare un workspace mentre il server lo usa.

## Patch locale

Se la modifica è stata applicata con `apply_dslm3_ui_workspaces.ps1`, il file `.dslm3_patch_state.json` identifica il backup. Prima di riprendere controllare se la patch è applicata, non applicata o parzialmente modificata. Il rollback standard usa il reverse della patch; il backup è una rete di sicurezza e non deve sovrascrivere modifiche successive senza scelta esplicita.
