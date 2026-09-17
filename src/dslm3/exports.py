from __future__ import annotations
import json
from pathlib import Path

import yaml
from lxml import etree
from dslm3.common import (
    DomainError,
    atomic_write,
    canonical,
    digest,
    dump_json,
    name_key,
    now,
    uid,
)
from dslm3.knowledge import Knowledge
from dslm3.temporal import comparable, validate_interval

NS = "http://gexf.net/1.3"


class Exports:
    def __init__(self, app):
        self.app, self.store, self.knowledge = app, app.store, Knowledge(app)

    def snapshot(self, schema_version=2, allow_incomplete=False):
        if schema_version not in {1, 2}:
            raise DomainError("schema_version", "Sono ammessi i profili 1 e 2.")
        if allow_incomplete and schema_version == 1:
            raise DomainError(
                "legacy_incomplete", "allow_incomplete richiede schema 2."
            )
        open_ = self.app.status()["counts"]["open_reconciliations"]
        if open_ and not allow_incomplete:
            raise DomainError(
                "reconciliation_required",
                "Eseguire la riconciliazione prima dell’export.",
                409,
            )
        objects = self.knowledge.objects(effective=schema_version == 2)
        entities = {}
        relations = []
        intervals = []
        traces = {"facts": {}, "relations": {}, "intervals": {}}
        for obj in objects:
            p = obj["payload"]
            kind = obj["kind"]
            supports = []
            for s in obj["supports"]:
                c = s["candidate_payload"]
                evid = c.get("evidence_id") or c.get("fragment_id") or c.get("chunk_id")
                rev = self.store.one(
                    "SELECT r.source_id,s.path FROM revisions r JOIN sources s ON s.id=r.source_id WHERE r.id=?",
                    (c["source_revision_id"],),
                )
                supports.append(
                    {
                        "candidate_record_id": s["candidate_id"],
                        "decision_id": s["decision_id"],
                        "source_revision_id": c["source_revision_id"],
                        "source_id": rev["source_id"],
                        "file_path": rev["path"],
                        "evidence_id": evid,
                        "evidence_text": c["evidence_text"],
                        "evidence_text_hash": digest(c["evidence_text"]),
                        "rule": s["rule"],
                        "temporal_evidence_ids": c.get("temporal_evidence_ids", []),
                    }
                )
            if kind == "fact":
                key = name_key(p["entity_name"])
                entities.setdefault(
                    key, {"name": p["entity_name"], "canonical_name": key, "facts": []}
                )
                fact = {
                    "fact_id": obj["id"],
                    **{k: v for k, v in p.items() if k != "entity_name"},
                    "status": "active",
                    "confidence": max(
                        (s["candidate_payload"]["confidence"] for s in obj["supports"]),
                        default="low",
                        key=lambda x: {"low": 0, "medium": 1, "high": 2}[x],
                    ),
                }
                if schema_version == 2:
                    fact["intervals"] = []
                entities[key]["facts"].append(fact)
                traces["facts"][obj["id"]] = supports
            elif kind == "relation":
                relations.append(
                    {
                        "relation_id": obj["id"],
                        **p,
                        "canonical_source_entity": name_key(p["source_entity"]),
                        "canonical_target_entity": name_key(p["target_entity"]),
                        "status": "active",
                        **({"intervals": []} if schema_version == 2 else {}),
                    }
                )
                traces["relations"][obj["id"]] = supports
                for label in [p["source_entity"], p["target_entity"]]:
                    entities.setdefault(
                        name_key(label),
                        {"name": label, "canonical_name": name_key(label), "facts": []},
                    )
            elif kind == "interval" and schema_version == 2:
                intervals.append({"interval_id": obj["id"], **p})
                traces["intervals"][obj["id"]] = supports
        if schema_version == 2:
            for entity in entities.values():
                for fact in entity["facts"]:
                    fact["intervals"] = [
                        i
                        for i in intervals
                        if i["target_subject_type"] == "fact"
                        and i["target_subject_id"] == fact["fact_id"]
                    ]
            for relation in relations:
                relation["intervals"] = [
                    i
                    for i in intervals
                    if i["target_subject_type"] == "relation"
                    and i["target_subject_id"] == relation["relation_id"]
                ]
        entity_list = [entities[k] for k in sorted(entities)]
        for e in entity_list:
            e["facts"].sort(key=lambda x: x["fact_id"])
        conflicts = self.knowledge.conflicts()
        sources = self.store.rows(
            "SELECT id AS source_id,path,status,current_revision FROM sources ORDER BY id"
        )
        revisions = self.store.rows(
            "SELECT id AS source_revision_id,source_id,sha256,size FROM revisions ORDER BY id"
        )
        content = {
            "metadata": {
                "schema_version": str(schema_version),
                "application": "DSLM3",
                "profile": "physical_legacy"
                if schema_version == 1
                else "effective_temporal",
                "counts": {
                    "entities": len(entity_list),
                    "facts": sum(len(e["facts"]) for e in entity_list),
                    "relations": len(relations),
                    "conflicts": len(conflicts),
                    "intervals": len(intervals),
                },
                "warnings": ["reconciliation_incomplete"] if open_ else [],
            },
            "entities": entity_list,
            "relations": relations,
            "conflicts": conflicts,
            "traceability": traces,
            "sources": sources,
            "source_revisions": revisions,
        }
        if schema_version == 2:
            content["intervals"] = intervals
        semantic_hash = digest(content)
        content["metadata"]["dsl_hash"] = semantic_hash
        sid = uid("DSL", content)
        with self.store.connect(True) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)",
                (sid, schema_version, semantic_hash, canonical(content), now()),
            )
        folder = self.app.root / "artifacts" / sid
        dump_json(folder / "dsl.json", content)
        atomic_write(
            folder / "dsl.yaml",
            yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
        )
        atomic_write(folder / "dsl.md", self.markdown(content))
        return {
            "id": sid,
            "hash": semantic_hash,
            "counts": content["metadata"]["counts"],
            "files": {
                ext: str((folder / f"dsl.{ext}").relative_to(self.app.root))
                for ext in ["json", "yaml", "md"]
            },
            "content": content,
        }

    @staticmethod
    def markdown(content):
        lines = [
            "# DSL Manager — conoscenza consolidata",
            "",
            f"Profilo {content['metadata']['schema_version']} · {content['metadata']['counts']['facts']} fatti · {len(content['relations'])} relazioni",
            "",
        ]
        for entity in content["entities"]:
            lines.extend(["## " + entity["name"], ""])
            for fact in entity["facts"]:
                lines.append(
                    "- **"
                    + fact["property_name"]
                    + "**: "
                    + canonical(fact["property_value"])
                )
                for t in content["traceability"]["facts"][fact["fact_id"]]:
                    lines.append(
                        f"  - Fonte: {t['file_path']} · candidato {t['candidate_record_id']} · evidenza {t['evidence_id']}"
                    )
            lines.append("")
        lines.extend(["## Relazioni", ""])
        for r in content["relations"]:
            lines.append(
                f"- {r['source_entity']} → {r['relation_type']} → {r['target_entity']}"
            )
        lines.extend(["", "## Conflitti", ""])
        for c in content["conflicts"]:
            lines.append(
                f"- {c['entity']}.{c['property']}: {canonical(c['left_value'])} / {canonical(c['right_value'])}"
            )
        return "\n".join(lines) + "\n"

    def snapshots(self):
        return [
            {
                "id": r["id"],
                "schema_version": r["schema_version"],
                "hash": r["content_hash"],
                "created_at": r["created_at"],
                "counts": json.loads(r["payload"])["metadata"]["counts"],
            }
            for r in self.store.rows("SELECT * FROM snapshots ORDER BY created_at DESC")
        ]

    def load(self, sid):
        row = self.store.one("SELECT payload FROM snapshots WHERE id=?", (sid,))
        if not row:
            raise DomainError("snapshot_missing", "Snapshot inesistente.", 404)
        return json.loads(row["payload"])

    def diff(self, before, after, cross_schema=False):
        a = self.load(before)
        b = self.load(after)
        if (
            a["metadata"]["schema_version"] != b["metadata"]["schema_version"]
            and not cross_schema
        ):
            raise DomainError(
                "cross_schema_required",
                "Confronto fra profili diversi: specificare cross_schema.",
            )

        def sections(x):
            return {
                "structure": {
                    **{
                        f["fact_id"]: {k: v for k, v in f.items() if k != "intervals"}
                        for e in x["entities"]
                        for f in e["facts"]
                    },
                    **{
                        r["relation_id"]: {
                            k: v for k, v in r.items() if k != "intervals"
                        }
                        for r in x["relations"]
                    },
                },
                "temporal": {i["interval_id"]: i for i in x.get("intervals", [])},
                "governance": {
                    **x["traceability"]["facts"],
                    **x["traceability"]["relations"],
                    **x["traceability"].get("intervals", {}),
                },
            }

        left = sections(a)
        right = sections(b)
        changes = []
        for category in left:
            for ident in sorted(set(left[category]) | set(right[category])):
                old = left[category].get(ident)
                new = right[category].get(ident)
                if old != new:
                    changes.append(
                        {
                            "category": category,
                            "object_id": ident,
                            "change": "added"
                            if old is None
                            else "removed"
                            if new is None
                            else "changed",
                            "before": old,
                            "after": new,
                            "causes": {
                                "before": left["governance"].get(ident, []),
                                "after": right["governance"].get(ident, []),
                            },
                        }
                    )
        payload = {
            "from": before,
            "to": after,
            "cross_schema": cross_schema,
            "changes": changes,
            "count": len(changes),
        }
        ident = uid("DIFF", payload)
        path = self.app.root / "artifacts" / ident / "diff.json"
        dump_json(path, payload)
        return {"id": ident, "file": str(path.relative_to(self.app.root)), **payload}

    def graph(
        self,
        snapshot_id,
        dynamic=False,
        mode="strict",
        include_sources=True,
        include_fact_nodes=True,
        include_conflicts=True,
    ):
        if mode not in {"strict", "omit", "separate"}:
            raise DomainError("graph_mode", "Modalità temporale non valida.")
        c = self.load(snapshot_id)
        if dynamic and c["metadata"]["schema_version"] != "2":
            raise DomainError("graph_profile", "Il grafo dinamico richiede DSL 2.")
        if (
            len(c["entities"]) + len(c["relations"])
            > self.store.config()["graph_max_elements"]
        ):
            raise DomainError("graph_budget", "Troppi nodi e archi.")
        formats = set()
        for i in c.get("intervals", []):
            if i["target_subject_type"] in {"fact", "relation"}:
                validate_interval(i, strict=True)
                formats.add(
                    "dateTime"
                    if "T" in (i.get("normalized_start") or i["normalized_end"])
                    else "date"
                )
        if dynamic and len(formats) > 1 and mode == "strict":
            raise DomainError(
                "mixed_timeformat", "Date e timestamp richiedono separate o omit."
            )
        profiles = (
            sorted(formats)
            if dynamic and mode == "separate" and len(formats) > 1
            else [next(iter(sorted(formats)), "date")]
        )
        files = []
        warnings = []
        for fmt in profiles:
            data, local_warnings = self._gexf(
                c,
                dynamic,
                fmt,
                mode,
                include_sources,
                include_fact_nodes,
                include_conflicts,
            )
            warnings.extend(local_warnings)
            path = (
                self.app.root
                / "artifacts"
                / snapshot_id
                / (
                    f"graph_{fmt}.gexf"
                    if len(profiles) > 1
                    else ("graph_dynamic.gexf" if dynamic else "graph.gexf")
                )
            )
            self.validate_gexf(data)
            atomic_write(path, data)
            files.append(str(path.relative_to(self.app.root)))
        report = {
            "snapshot_id": snapshot_id,
            "dynamic": dynamic,
            "mode": mode,
            "files": files,
            "warnings": warnings,
            "validation": "offline_xsd_and_semantic",
            "include_sources": include_sources,
            "include_fact_nodes": include_fact_nodes,
            "include_conflicts": include_conflicts,
        }
        dump_json(
            self.app.root / "artifacts" / snapshot_id / "graph_report.json", report
        )
        return report

    def _gexf(
        self,
        c,
        dynamic,
        fmt,
        mode,
        include_sources=True,
        include_fact_nodes=True,
        include_conflicts=True,
    ):
        def sub(parent, tag, **attrs):
            return etree.SubElement(parent, "{" + NS + "}" + tag, **attrs)

        root = etree.Element("{" + NS + "}gexf", nsmap={None: NS}, version="1.3")
        graph = sub(
            root,
            "graph",
            defaultedgetype="directed",
            mode="dynamic" if dynamic else "static",
        )
        if dynamic:
            graph.set("timeformat", fmt)
        for class_, names in [
            (
                "node",
                ["kind", "object_id", "property_name", "property_value", "provenance"],
            ),
            ("edge", ["relation_type", "provenance"]),
        ]:
            declarations = sub(
                graph, "attributes", **{"class": class_, "mode": "static"}
            )
            for name in names:
                sub(declarations, "attribute", id=name, title=name, type="string")
        nodes = sub(graph, "nodes")
        edges = sub(graph, "edges")
        warnings = []
        node_times = {}
        ids = {}
        fact_ids = {}
        count = 0

        def attrs(element, values):
            holder = sub(element, "attvalues")
            for key, value in values.items():
                if value is not None:
                    sub(
                        holder,
                        "attvalue",
                        **{
                            "for": key,
                            "value": value
                            if isinstance(value, str)
                            else canonical(value),
                        },
                    )

        def filtered(items):
            accepted = []
            for i in items:
                form = (
                    "dateTime"
                    if "T" in (i.get("normalized_start") or i["normalized_end"])
                    else "date"
                )
                if form == fmt:
                    accepted.append(i)
                else:
                    warnings.append(
                        {
                            "reason": "interval_omitted_in_profile",
                            "interval_id": i["interval_id"],
                            "profile": fmt,
                        }
                    )
            return list(
                {
                    canonical([i.get("normalized_start"), i.get("normalized_end")]): i
                    for i in accepted
                }.values()
            )

        def spells(element, items):
            if not dynamic or not items:
                return
            holder = sub(element, "spells")
            for i in sorted(items, key=lambda x: x.get("normalized_start") or ""):
                sub(
                    holder,
                    "spell",
                    **{
                        k: v
                        for k, v in [
                            ("start", i.get("normalized_start")),
                            ("end", i.get("normalized_end")),
                        ]
                        if v is not None
                    },
                )

        def node(ident, label, kind, times=None, **values):
            nonlocal count
            count += 1
            times = times or []
            node_times[ident] = times
            element = sub(nodes, "node", id=ident, label=label)
            attrs(element, {"kind": kind, "object_id": ident, **values})
            spells(element, times)

        def contained(interval, parents):
            if not parents:
                return True
            for parent in parents:
                start_ok = (
                    not parent.get("normalized_start")
                    or interval.get("normalized_start")
                    and comparable(parent["normalized_start"])
                    <= comparable(interval["normalized_start"])
                )
                end_ok = (
                    not parent.get("normalized_end")
                    or interval.get("normalized_end")
                    and comparable(interval["normalized_end"])
                    <= comparable(parent["normalized_end"])
                )
                if start_ok and end_ok:
                    return True
            return False

        def edge(ident, source, target, label, times=None, provenance=None):
            nonlocal count
            times = times or []
            if dynamic and any(
                not contained(i, node_times[source])
                or not contained(i, node_times[target])
                for i in times
            ):
                if mode == "strict":
                    raise DomainError(
                        "edge_outside_node_spells",
                        "Un intervallo dell’arco esce dagli intervalli dei nodi.",
                    )
                warnings.append(
                    {"reason": "edge_omitted_outside_node_spells", "relation_id": ident}
                )
                return
            count += 1
            element = sub(
                edges, "edge", id=ident, source=source, target=target, label=label
            )
            attrs(element, {"relation_type": label, "provenance": provenance})
            spells(element, times)

        for e in c["entities"]:
            nid = uid("NODE", e["canonical_name"])
            ids[e["canonical_name"]] = nid
            # An undated fact does not imply that its entity exists only during another fact's spell.
            times = (
                filtered([i for f in e["facts"] for i in f.get("intervals", [])])
                if dynamic
                and e["facts"]
                and all(f.get("intervals") for f in e["facts"])
                else []
            )
            node(nid, e["name"], "entity", times, property_value=e["facts"])
        if include_sources:
            for source in c["sources"]:
                node(
                    source["source_id"], source["path"], "source", property_value=source
                )
        for e in c["entities"]:
            for fact in e["facts"]:
                fid = fact["fact_id"]
                times = filtered(fact.get("intervals", [])) if dynamic else []
                traces = c["traceability"]["facts"][fid]
                entity = ids[e["canonical_name"]]
                if include_fact_nodes:
                    fact_ids[fid] = fid
                    node(
                        fid,
                        e["name"] + "." + fact["property_name"],
                        "fact",
                        times,
                        property_name=fact["property_name"],
                        property_value=fact["property_value"],
                        provenance=traces,
                    )
                    edge(uid("MENTIONS", fid), fid, entity, "mentions", times, traces)
                else:
                    fact_ids[fid] = entity
                if include_sources:
                    for source in sorted({t["source_id"] for t in traces}):
                        edge(
                            uid("DERIVES", [fid, source]),
                            fact_ids[fid],
                            source,
                            "derives_from",
                            times,
                            traces,
                        )
        for r in c["relations"]:
            times = filtered(r.get("intervals", [])) if dynamic else []
            edge(
                r["relation_id"],
                ids[r["canonical_source_entity"]],
                ids[r["canonical_target_entity"]],
                r["relation_type"],
                times,
                c["traceability"]["relations"][r["relation_id"]],
            )
        if include_conflicts:
            for conflict in c["conflicts"]:
                node(
                    conflict["id"],
                    conflict["entity"] + "." + conflict["property"],
                    "conflict",
                    property_value=conflict,
                )
                for fid in (conflict["left"], conflict["right"]):
                    if fid in fact_ids:
                        target = fact_ids[fid]
                        edge(
                            uid("CONFLICT_EDGE", [conflict["id"], fid]),
                            conflict["id"],
                            target,
                            "conflicts_with",
                            node_times[target],
                        )
        if count > self.store.config()["graph_max_elements"]:
            raise DomainError(
                "graph_budget", "Troppi nodi e archi, inclusi provenienza e conflitti."
            )
        return etree.tostring(
            root, encoding="UTF-8", xml_declaration=True, pretty_print=True
        ), warnings

    @staticmethod
    def validate_gexf(data):
        resource = Path(__file__).parent / "resources/gexf"
        manifest = json.loads((resource / "manifest.json").read_text())
        for item in manifest["resources"]:
            if digest((resource / item["file"]).read_bytes()) != item["sha256"]:
                raise DomainError("schema_integrity", "Risorsa XSD modificata.")

        class LocalResolver(etree.Resolver):
            def resolve(self, url, public_id, context):
                target = resource / Path(url).name
                if (
                    target.parent != resource
                    or not target.name.endswith(".xsd")
                    or not target.exists()
                ):
                    raise DomainError(
                        "external_schema", "Risoluzione XSD esterna vietata."
                    )
                return self.resolve_filename(str(target), context)

        parser = etree.XMLParser(no_network=True, resolve_entities=False)
        parser.resolvers.add(LocalResolver())
        schema = etree.XMLSchema(etree.parse(str(resource / "gexf.xsd"), parser))
        document = etree.fromstring(data, parser)
        schema.assertValid(document)
        ns = {"g": NS}
        nodes = {x.get("id") for x in document.findall(".//g:node", ns)}
        for edge in document.findall(".//g:edge", ns):
            if edge.get("source") not in nodes or edge.get("target") not in nodes:
                raise DomainError("graph_missing_endpoint", "Nodo estremo assente.")
        for spell in document.findall(".//g:spell", ns):
            if (
                spell.get("start")
                and spell.get("end")
                and comparable(spell.get("start")) > comparable(spell.get("end"))
            ):
                raise DomainError("graph_spells", "Intervallo grafo invertito.")
        return True
