"""Print the judge manifest (JSON) of every generated video. Run from the PhyCoVE data root."""
import json
from pathlib import Path
from fractions import Fraction

rows = []
for split in ("sim","real"):
    release = Path("releases/PhyCoVE")
    predictions = Path("predictions/PhyCoVE")
    if split == "real":
        release /= "real"
        predictions /= "real"
    meta = {r["id"]:r for r in map(json.loads,(release/"metadata.jsonl").read_text().splitlines())}
    for video in sorted(predictions.glob("quantitative_en/*/videos/*/*.mp4")):
        case = video.parent.name+"/"+video.stem
        r = meta[case]
        src,gt = release/r["source_file_name"],release/r["file_name"]
        assert all(p.is_file() and p.stat().st_size for p in (video,src,gt)), video
        event = r["application_time_sec"]
        assert abs((r["applies_from_frame"]-1)/float(Fraction(r["fps"]))-event)<1e-4,case
        assert r["prompt_quantitative_en"].strip(),case
        rows.append(dict(split=split,scene=r["scene"],case=r["case_id"],model=video.parents[2].name,
            event=event,instruction=r["prompt_quantitative_en"],source=str(src),gt=str(gt),candidate=str(video)))
assert len({(r["scene"],r["case"],r["model"]) for r in rows}) == len(rows)
print(json.dumps(rows,indent=2))
