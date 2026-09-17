# Origine del codice e dipendenze

DSLM3 è una riscrittura eseguita per il proprietario di `DanieleBarbiero/dsl_manager-v1`, baseline `c443b6a457b78229517a481fc5850dc8b44ecc3a`. Non è stata effettuata alcuna scrittura su GitHub. Questa consegna non attribuisce una nuova licenza al codice del proprietario.

## Riutilizzo esplicito della baseline

- `src/dslm3/vendor/ooxml_preflight.py`: preflight OOXML e manifest Excel.
- `src/dslm3/vendor/workbook_regions.py`: identificazione delle regioni del workbook.
- `src/dslm3/vendor/canonical.py`: funzioni canoniche necessarie ai due moduli.
- Fixture strutturali Excel e sei fonti del laboratorio Vega, conservate per regressione.

Gli import dei moduli riutilizzati sono adattati al namespace `dslm3.vendor`; la formattazione è uniformata. La parità del manifest è verificata contro il golden della v1. Il resto del motore applicativo, servizio, persistenza, governance, UI, AI e parser SQL appartiene alla riscrittura M3.

## Componenti di terzi

Le dipendenze vengono installate dai loro distributori e conservano le rispettive licenze: Docling e docling-core, SQLGlot, FastAPI/Starlette, Uvicorn, PyTorch, OpenCV, NumPy, lxml, openpyxl, xlrd, pyxlsb, odfpy, PyYAML, Beautiful Soup, charset-normalizer, psutil e gli strumenti di test. `requirements-tested-linux.txt` registra le versioni effettivamente installate; non costituisce una sublicenza.

Le risorse GEXF 1.3 mantengono il file `src/dslm3/resources/gexf/LICENSE.txt` e il manifest SHA-256 di origine. I modelli scaricati da Docling/RapidOCR mantengono le condizioni dei rispettivi fornitori; non sono inclusi nei sorgenti consegnati.
