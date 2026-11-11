"""Spike S3, step 1: versions, licences, regions and sizes of the two atlases.

Throwaway code, not part of the package. Run from the repo root:

    SIIBRA_CACHEDIR=data/cache/s3/siibra uv run --group spike-s3 python spikes/s3/atlases.py

Downloads go to data/cache/s3/ (git-ignored). Each atlas is written to its own results file
(spikes/s3/results/waxholm.json, julich.json): nothing derived mixes the two atlases, because
their licences (CC BY-SA and CC BY-NC-SA) cannot be combined.

Requests use a generic User-Agent with no personal contact. Calls are few and in series:
one DataCite lookup per DOI, the BrainGlobe S3 bucket listing and the siibra configuration.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests
import requests.utils

USER_AGENT = "synaptica-spike/0.1"
# siibra and BrainGlobe use requests internally: give them the same generic User-Agent.
requests.utils.default_user_agent = lambda *_: USER_AGENT

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache" / "s3"
RESULTS = ROOT / "spikes" / "s3" / "results"
BG_ATLAS = "whs_sd_rat_39um"
WAXHOLM_V401_KG = "2cf40e61-fae1-4ab3-b7de-cb8fdfa19b70"  # from the v4 KG record, otherVersions
WAXHOLM_TEMPLATE_DOI = "10.25493/DTSG-ZBS"  # cited by the v4.01 record as its MRI volume
BG_MESHES = (
    "brainglobe/atlas/annotation-sets/whs_sd_rat-annotation/3_0/annotations.precomputed/mesh"
)

# Test regions (PLAN.md): name fragments to look for, per atlas. Only lookups; whether two
# regions are equivalent, and how much, is Sofía's call and is not recorded here.
WAXHOLM_TEST = {"surface": [408], "internal": [1021], "third": [501]}  # M1, HF, Am-u
JULICH_TEST = {
    "surface": ["Area 4a (PreCG)", "Area 4p (PreCG)"],
    "internal": [
        "CA1 (Hippocampus)",
        "CA2 (Hippocampus)",
        "CA3 (Hippocampus)",
        "DG (Hippocampus)",
        "Subc (Hippocampus, Subicular complex)",
    ],
    "third": [
        "CM (Amygdala)",
        "LB (Amygdala)",
        "SF (Amygdala)",
        "Astr (Amygdala)",
        "VTM (Amygdala)",
        "IF (Amygdala)",
        "MF (Amygdala)",
    ],
}


def datacite(doi: str) -> dict:
    """Licence and version of a DOI as registered in DataCite (EBRAINS KG registers there)."""
    r = requests.get(f"https://api.datacite.org/dois/{doi}", timeout=30)
    time.sleep(1)
    if r.status_code == 404:
        return {"doi": doi, "found": False}
    r.raise_for_status()
    a = r.json()["data"]["attributes"]
    return {
        "doi": doi,
        "title": a["titles"][0]["title"],
        "publisher": a.get("publisher"),
        "version": a.get("version"),
        "rights": [
            {k: x.get(k) for k in ("rights", "rightsIdentifier", "rightsUri")}
            for x in a.get("rightsList", [])
        ],
        "url": a.get("url"),
    }


def kg_search(uuid: str) -> dict:
    """Title, licence and release date of a KG dataset version (public search API, no token)."""
    r = requests.get(f"https://search.kg.ebrains.eu/api/groups/public/documents/{uuid}", timeout=30)
    time.sleep(1)
    r.raise_for_status()
    d = r.json()
    f = d["fields"]
    return {
        "kg_dataset_version_id": uuid,
        "title": d["title"],
        "license": f["license_info"],
        "released": (f.get("releasedAt") or {}).get("value"),
        "url": f"https://search.kg.ebrains.eu/instances/{uuid}",
    }


def kg(parcellation) -> dict:
    """The EBRAINS Knowledge Graph dataset version behind a siibra parcellation."""
    (d,) = [x for x in parcellation.datasets if type(x).__name__ == "EbrainsV3DatasetVersion"]
    raw = d._detail  # the KG record as siibra fetched it
    dois = raw.get("doi") or []
    doi = (dois[0] if isinstance(dois, list) and dois else dois) or None
    if isinstance(doi, dict):
        doi = doi.get("identifier")
    doi = doi.split("doi.org/", 1)[-1] if doi else None
    return {
        "kg_dataset_version_id": d.id,
        "name": d.name,
        "version": d.version_identifier,
        "license": raw.get("license"),
        "ebrains_page": d.ebrains_page,
        "doi": doi,
        "paper": parcellation.urls,
        "datacite": datacite(doi) if doi else None,
    }


def waxholm(siibra) -> dict:
    import s3fs
    from brainglobe_atlasapi import BrainGlobeAtlas

    atlas = BrainGlobeAtlas(BG_ATLAS, brainglobe_dir=CACHE / "brainglobe", check_latest=False)
    meta = {k: v for k, v in atlas.metadata.items() if isinstance(v, (str, int, float, list))}
    structs = list(atlas.structures.values())
    child_ids = {s["structure_id_path"][-2] for s in structs if len(s["structure_id_path"]) > 1}
    leaves = [s for s in structs if s["id"] not in child_ids]

    # Mesh sizes from the bucket listing: no need to download the 300+ files to weigh them.
    fs = s3fs.S3FileSystem(anon=True, config_kwargs={"user_agent": USER_AGENT})
    sizes = {
        Path(f["name"]).name: f["size"]
        for f in fs.ls(BG_MESHES, detail=True)
        if f["type"] == "file"
    }
    id_sizes = {int(k): v for k, v in sizes.items() if k.isdigit()}

    # The KG view of the same atlas (siibra), for the licence BrainGlobe does not carry.
    # siibra stops at v4; BrainGlobe ships the three regions that v4.01 added (per the KG).
    p = siibra.parcellations["waxholm v4"]
    acronyms = {s["acronym"] for s in structs}
    v401_new = {"msp5t", "5n", "AOA-u"}

    def region(i: int) -> dict:
        s = atlas.structures[i]
        p_desc = [d for d in structs if i in d["structure_id_path"] and d["id"] != i]
        return {
            "id": i,
            "acronym": s["acronym"],
            "name": s["name"],
            "path": [atlas.structures[x]["acronym"] for x in s["structure_id_path"]],
            "descendants": [d["acronym"] for d in p_desc],
            "mesh_bytes_raw": id_sizes.get(i),
        }

    return {
        "atlas": "Waxholm Space atlas of the Sprague Dawley rat brain",
        "via": f"brainglobe-atlasapi, atlas {BG_ATLAS}",
        "brainglobe_metadata": meta,
        "brainglobe_has_licence_field": any("licen" in k.lower() for k in atlas.metadata),
        "content_version": "v4.01" if v401_new <= acronyms else "v4 or older",
        "v401_regions_present": sorted(v401_new & acronyms),
        "kg_parcellation": {"name": p.name, "version": p.version, "id": p.id},
        "kg": kg(p),
        "kg_v401": kg_search(WAXHOLM_V401_KG),
        # The MRI template (not the delineations) is a separate dataset with its own licence.
        "template_datacite": datacite(WAXHOLM_TEMPLATE_DOI),
        "regions": {"structures_total": len(structs), "leaves": len(leaves)},
        "id_format": "integer; BrainGlobe id == annotation value in the volume",
        "meshes": {
            "files": len(sizes),
            "bytes_raw_total": sum(sizes.values()),
            "format": "neuroglancer precomputed (legacy single-resolution), uncompressed",
            "brain_root_mesh_bytes": id_sizes.get(1000) or id_sizes.get(10000),
        },
        "test_regions": {k: [region(i) for i in v] for k, v in WAXHOLM_TEST.items()},
    }


def julich(siibra) -> dict:
    p = siibra.parcellations["julich 3.1"]
    versions = sorted(x.name for x in siibra.parcellations if "Julich-Brain" in x.name)
    mni = siibra.spaces["mni152"]
    labelled = p.get_map(space=mni, maptype="labelled")
    fsavg = p.get_map(space="fsaverage", maptype="labelled")

    img = labelled.fetch()  # the MPM in MNI152 2009c (one NIfTI)
    nii = CACHE / "julich_mpm_mni152.nii.gz"
    img.to_filename(nii)

    mapped = set(labelled.regions)

    def region(name: str) -> dict:
        r = p.get_region(name)
        # The MPM maps some areas as a whole (e.g. "CM (Amygdala) left") even when the tree
        # has finer subdivisions: record the mapped level, whichever it is.
        sides = [f"{r.name} {side}" for side in ("left", "right")]
        names = sides if set(sides) <= mapped else [x.name for x in r.leaves if x.name in mapped]
        labels = {}
        for n in names:
            idx = labelled.get_index(n)
            labels[n] = {"label": idx.label, "volume": idx.volume}
        return {
            "name": r.name,
            "id": r.id,
            "path": [a.name for a in r.ancestors][::-1],
            "subdivisions_in_tree": len(r.leaves),
            "labels_mni152": labels,
        }

    return {
        "atlas": "Julich-Brain Cytoarchitectonic Atlas",
        "via": f"siibra {siibra.__version__}",
        "versions_in_siibra": versions,
        "parcellation": {
            "name": p.name,
            "version": p.version,
            "id": p.id,
            "is_newest_version": p.is_newest_version,
        },
        "kg": kg(p),
        "regions": {"leaves": len(p.leaves), "labelled_in_mni152_mpm": len(labelled.regions)},
        "id_format": "siibra/KG region id (string); MPM label is an integer per area and side",
        "mpm": {
            "space": mni.name,
            "shape": list(img.shape),
            "dtype": str(img.get_data_dtype()),
            "bytes_nifti_gz": nii.stat().st_size,
        },
        "meshes": {
            "volumetric": "none: MPM is a label volume; meshes must be generated (marching cubes)",
            "fsaverage_labelled_surface": fsavg is not None,
            "fsaverage_provides_mesh": bool(fsavg and fsavg.provides_mesh),
        },
        "test_regions": {k: [region(n) for n in v] for k, v in JULICH_TEST.items()},
    }


def main() -> None:
    import siibra

    RESULTS.mkdir(parents=True, exist_ok=True)
    for name, fn in (("waxholm", waxholm), ("julich", julich)):
        out = RESULTS / f"{name}.json"
        out.write_text(json.dumps(fn(siibra), indent=2, ensure_ascii=False, default=str) + "\n")
        print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
