# DSLM3 — punto di ingresso

Il progetto corrente è costituito dai **singoli file di questa cartella**, con `src`, `tests`, `scripts`, `docs` e `reports`. Non usare `dslm3_checkpoint.zip` per riprendere il lavoro: è un checkpoint storico precedente alla consegna. Non salvare nuovi ZIP come memoria di progetto.

1. Leggere `README.md` per l'avvio.
2. Leggere `docs/obiettivi.md`, l'ultima sezione di `docs/diario_tecnico.md` e `docs/protocollo_ripresa.md` per lo stato corrente e il punto esatto da cui riprendere.
3. Leggere `reports/deterministic_core/closure_20260930/acceptance.md` e `docs/rapporto_core_deterministico.md` per la modifica corrente. `docs/rapporto_finale.md` resta il rapporto del rilascio precedente.
4. Leggere `docs/formati_e_limiti.md` e `docs/matrice_parita.md` prima di estendere o dichiarare coperture.
5. `release_manifest.json` identifica il baseline consegnato finché una modifica non supera nuovamente i gate e il manifest non viene rigenerato; i report in `reports/precedente` sono esclusivamente storici.

Per la modifica corrente lavorare sul branch `feat/deterministic-core-upgrade`, baseline `a7117e061b393123e3b7b2ec22bf171687756447`, senza creare altri branch né effettuare push o scritture remote. Salvare i singoli file localmente; aggiornare diario, obiettivi e protocollo con gli stessi risultati. Uno step fallito resta aperto. Non dichiarare prove di una versione precedente come prove correnti. `docs/protocollo_ripresa_precedente.md` resta storico.

Per installazione e prove Windows usare l'interprete Python 3.12 x64 del progetto. Il wrapper `scripts/check_deterministic_core.ps1` è compatibile con PowerShell 5.1; non cambia l'Execution Policy. Le prove Linux del vecchio rilascio non certificano questo aggiornamento.
