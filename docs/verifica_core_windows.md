# Verifica del core su Windows PowerShell 5.1

Usare Python 3.12 x64 del progetto. Il launcher esterno presente nel checkout usa
`C:\_Support\.venv_dslm3\Scripts\python.exe`; è anche possibile indicare un
ambiente locale o `PROJECT_PYTHON`. Python 3.14 trovato nel PATH non è il runtime
del progetto. I pin applicativi rimangono quelli di `pyproject.toml`.

Da Windows PowerShell 5.1, nella radice del repository:

```powershell
$ProjectPython = 'C:\_Support\.venv_dslm3\Scripts\python.exe'
& $ProjectPython -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Installazione fallita' }
& $ProjectPython -m playwright install chromium --only-shell
if ($LASTEXITCODE -ne 0) { throw 'Browser non disponibile' }
& '.\scripts\check_deterministic_core.ps1' -ProjectPython $ProjectPython `
    -RuntimeRoot 'C:\_Support\dslm3_acceptance' `
    -ReportDirectory '.\reports\deterministic_core\closure_20260930' `
    -V1Root '..\dsl_manager-v1'
if ($LASTEXITCODE -ne 0) { throw 'Acceptance fallita' }
```

Il wrapper è ASCII, non richiede PowerShell 7, Bash o WSL, controlla runtime e
codici di uscita e non modifica execution policy. Il runner crea un nuovo
sottopercorso runtime a ogni esecuzione. I report sono UTF-8 e i log catturano
l'output binario dei processi. Il test oracle richiede il repository v1 locale
con il commit specificato: l'assenza non viene trattata come pass o skip tacito.

Il runner esegue pip check, lint F, suite completa, Vega deterministico, Vega
integrato (AI simulata dichiarata), browser desktop/mobile e wheel installato
fuori dai sorgenti. Verifica i Git blob delle sei fixture e ne materializza i byte
in una directory isolata. `acceptance.json` include comandi, exit code, versioni,
SHA/dirty, hash del codice, G01–G18 e COV/BIZ. Non modificare il codice mentre gira:
il runner controlla che lo snapshot dei sorgenti non sia cambiato.

Se la shell corrente è PowerShell 7, invocare esplicitamente il runtime richiesto:

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoLogo -NoProfile `
    -File '.\scripts\check_deterministic_core.ps1' `
    -ProjectPython 'C:\_Support\.venv_dslm3\Scripts\python.exe' `
    -RuntimeRoot 'C:\_Support\dslm3_acceptance' `
    -ReportDirectory '.\reports\deterministic_core\nuova_verifica' `
    -V1Root '..\dsl_manager-v1'
if ($LASTEXITCODE -ne 0) { throw 'Acceptance fallita' }
```

L'esito positivo richiede PowerShell 5.1 registrato; un'esecuzione con 7 viene
distinta come G17 non verificato. Dopo la chiusura, `python
scripts/export_deterministic_patch.py --report-dir reports/deterministic_core/closure_20260930` crea la patch con indici temporanei, verifica
applicazione sulla baseline e applicazione inversa sullo snapshot modificato,
conserva l'indice reale e scrive `delivery.json`. Il controllo rifiuta sorgenti
applicativi diversi dallo snapshot collaudato.

## Upgrade di un workspace esistente

1. Arrestare UI, CLI e worker che usano il workspace. Conservare una copia a
   freddo dell'intera directory, inclusi corpus, oggetti e artefatti; non copiare
   soltanto SQLite. Non operare sulla directory originale durante la prova.
2. Aggiungere al comando precedente `-ColdWorkspace 'C:\dati\workspace_copia_a_freddo'`.
   Il runner legge quella copia, ne crea un'altra nel runtime del test, esegue
   migrazione, parse, derive e `coverage --check` e registra gli esiti. Non cambia
   le policy o le decisioni e non approva implicitamente le nuove proposte.
3. Controllare il rapporto, le componenti bloccate e le nuove pending. Eseguire
   review esplicita, merge e reconcile sulla copia se si vuole verificare anche
   il nuovo snapshot. I test automatici verificano separatamente la migrazione
   da schema 2 con conservazione dello storico e delle review.

Il `release_manifest.json` preesistente identifica una consegna storica. Il suo
inventario non certifica questa modifica: il riferimento corrente è il rapporto
di acceptance con hash dello snapshot, non i vecchi conteggi 79/89 o 52 evidence.


## G18 e aggiornamenti soltanto documentali

Il runner cattura sia lo snapshot del pacchetto sia `executable_snapshot` con
hash di sorgenti, test, fixture, configurazione di build e harness. G18 confronta
branch, HEAD, baseline e branch padre, controlla diff e inventario dei file,
legge gli esiti JUnit/Vega/browser e associa hash ai log.

I controlli manuali `diff_readability_and_scope`, `oracle_mapping_and_exceptions`
e `documentation_claims` richiedono una revisione reale nominata, con motivazione,
in `docs/revisione_chiusura_core.json`. Il record riporta gli hash dei file
eseguibili e dei documenti esaminati; un record assente o non coerente fallisce G18.
Non generare un'attestazione positiva per aggirare una verifica mancante.

Dopo la suite è possibile aggiornare soltanto il rapporto con gli esiti osservati,
rinnovare la revisione dei documenti e rieseguire:

```powershell
& $ProjectPython scripts/acceptance_closure.py --report-dir reports/deterministic_core/closure_20260930
if ($LASTEXITCODE -ne 0) { throw 'G18 non soddisfatto' }
```

Questo comando non riesegue né riassegna i test: rifiuta un HEAD o uno snapshot
eseguibile diverso da quello registrato. Qualsiasi modifica a sorgenti, test,
fixture o harness richiede una nuova acceptance completa. Le prove storiche in
`final/` non vengono aggiornate. La patch locale esclude i contenitori patch
storici e i propri riferimenti circolari; il manifest 3.0.0 resta storico.


Il diff completo dalla baseline include anche patch e log storici. `diff_check_all.txt`
conserva l'esito grezzo di `git diff --check` su tutto il contenuto: le righe di
contesto di un file patch e l'output storico di pytest possono contenere spazi
finali legittimi. Il controllo obbligatorio di whitespace riguarda sorgenti,
test, harness e documentazione; la revisione manuale dichiara questa distinzione.
I report storici non vengono riscritti per ripulire il diff.


L'inventario di consegna coincide con il delta dalla baseline più i file nuovi.
Il checkout contiene un workspace storico tracciato: G18 ne registra i blob e
lo preserva, ma non lo include nella patch se invariato. Un database o qualunque
file sotto workspace/ nuovo o modificato rimane un errore, coperto da test.
