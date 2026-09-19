# DSLM3 — punto di ingresso

Il progetto corrente è costituito dai **singoli file di questa cartella**, con `src`, `tests`, `scripts`, `docs` e `reports`. Non usare `dslm3_checkpoint.zip` per riprendere il lavoro: è un checkpoint storico precedente alla consegna. Non salvare nuovi ZIP come memoria di progetto.

1. Leggere `README.md` per l'avvio.
2. Leggere `docs/obiettivi.md`, l'ultima sezione di `docs/diario_tecnico.md` e `docs/protocollo_ripresa.md` per lo stato corrente e il punto esatto da cui riprendere.
3. Leggere `docs/rapporto_finale.md` come rapporto del rilascio verificato precedente; non usarlo per attribuire prove a modifiche successive.
4. Leggere `docs/formati_e_limiti.md` e `docs/matrice_parita.md` prima di estendere o dichiarare coperture.
5. `release_manifest.json` identifica il baseline consegnato finché una modifica non supera nuovamente i gate e il manifest non viene rigenerato; i report in `reports/precedente` sono esclusivamente storici.

Per modifiche future: cambiare uno step alla volta, verificare l'obiettivo con prove adeguate, salvare i file modificati **direttamente su Drive**, poi aggiornare diario, obiettivi e protocollo di ripresa con gli stessi risultati. Uno step fallito resta aperto. Non dichiarare prove di una versione precedente come prove di quella corrente. Mantenere gli identificativi Drive dei file aggiornati e conservare lo storico. `docs/protocollo_ripresa_precedente.md` resta storico e non va trasformato nel protocollo corrente.

Vincolo di progetto: GitHub soltanto lettura. Nessun push, commit remoto, issue o PR. Per installazione e prove Windows usare l'interprete Python 3.12 del progetto; la consegna attuale è stata eseguita su Linux.
