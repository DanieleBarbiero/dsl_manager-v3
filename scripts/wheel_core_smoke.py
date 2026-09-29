"""Load the installed wheel outside the checkout, preserving the project runtime."""

from pathlib import Path
import sys

installed = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(installed))
import dslm3
from dslm3.service import Application
from dslm3.knowledge import Knowledge
from dslm3.provenance import code_provenance

assert Path(dslm3.__file__).resolve().is_relative_to(installed)
package = Path(dslm3.__file__).parent
assert (package / "static/app.js").is_file()
assert len(list((package / "resources/vega").rglob("*.*"))) == 6
assert list((package / "resources/gexf").glob("*.xsd"))
provenance = code_provenance()
assert provenance["head"] is None and provenance["source_file_count"] > 30, provenance
print("installed code provenance:", provenance)
app = Application(sys.argv[2])
app.load_vega()
parsed = app.parse_all()
assert parsed["success"] == 6 and parsed["errors"] == parsed["partial"] == 0, parsed
Knowledge(app).derive()
assert app.coverage(check=True)["complete"]
print("wheel: six real sources, resources, deterministic derivation passed")
