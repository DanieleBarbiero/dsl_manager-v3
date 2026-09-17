# DSLM3 — DSL Manager 3.0.0

Applicazione locale per trasformare file tecnici e documentali in conoscenza verificabile: **fonti → evidenze → proposte → review → merge → DSL e grafo**. La UI web è il punto d'ingresso; ogni operazione è disponibile anche dalla CLI.

## Avvio su Windows

1. Copia tutta questa cartella sul PC, conservandone la struttura. Serve **Python 3.12 a 64 bit**.
2. Esegui **`installa.cmd`** una volta. La prima installazione richiede Internet e diversi GB liberi per le dipendenze.
3. Esegui **`avvia.cmd`**. Si apre `http://127.0.0.1:8765`.
4. In Panoramica scegli **Carica il laboratorio**. In Impostazioni scegli **Profilo conservativo**, poi **Elabora il corpus**.

L'esecuzione Windows non è stata provata in questo ambiente Linux. Gli script usano un ambiente virtuale nel progetto, percorsi tra virgolette e lo stesso Python 3.12 richiesto dal pacchetto. Non servono WSL, Docker, Node o un account AI.

## Avvio su Linux

```bash
bash installa.sh
bash avvia.sh
```

È possibile scegliere workspace e porta dalla CLI:

```bash
.venv/bin/python -m dslm3 --workspace ./mio_workspace serve --port 8765
```

Su Windows sostituire `.venv/bin/python` con `.venv\Scripts\python.exe`. Per fermare il server usare Ctrl+C nella console. Il workspace rimane persistente.

## Cosa aspettarsi

- Acquisizione ricorsiva, esclusioni, revisioni SHA-256 e copie dei byte originali.
- SQL multi-dialetto, Oracle PL/SQL, Forms XML, log, Excel strutturale e documenti tramite Docling reale.
- Proposte con citazioni e localizzatori; review append-only, correzioni, supporti multipli e riconciliazione.
- Segnali temporali separati dalla validità semantica; propagazione solo esplicita.
- Pacchetti AI esportabili e rientro JSONL validato. L'applicazione **non chiama automaticamente un modello esterno**.
- Snapshot JSON/YAML/Markdown, confronto tra snapshot e GEXF statico/dinamico con provenienza.

La review manuale è il default. Il profilo conservativo abilita soltanto policy tecniche nominate. Le proposte AI e temporali restano da valutare; confermare non equivale a eseguire il merge.

## Documenti

- [Manuale operativo](docs/manuale_operativo.md)
- [Formati e limiti](docs/formati_e_limiti.md)
- [Architettura](docs/architettura.md)
- [Obiettivi e gate](docs/obiettivi.md)
- [Diario tecnico](docs/diario_tecnico.md)
- [Rapporto di consegna](docs/rapporto_finale.md)
- [Avvisi sul codice riutilizzato](THIRD_PARTY_NOTICES.md)

`reports/precedente` contiene prove storiche recuperate dal checkpoint interrotto. Per la consegna valgono i report indicati nel rapporto finale. Codice, test, fixture, documenti e prove sono salvati come singoli file nella cartella Drive del progetto.

## Verifiche riproducibili

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python -m dslm3.lab --workspace ./runtime/vega_nuovo --report ./reports/vega_locale.json
.venv/bin/python -m playwright install chromium --only-shell
.venv/bin/python scripts/browser_check.py ./runtime/browser_nuovo
.venv/bin/python scripts/pdf_check.py --workspace ./runtime/pdf_nuovo --report ./reports/pdf_locale.json
```

I laboratori richiedono workspace nuovi. Il PDF e le immagini possono scaricare modelli Docling alla prima conversione. Le risposte AI del laboratorio sono fixture controllate e dichiarate.
