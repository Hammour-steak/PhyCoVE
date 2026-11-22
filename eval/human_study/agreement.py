"""Rank agreement of the automatic metrics with the human preference study.

Usage: python agreement.py VALUES.json

VALUES.json gives one value per model for the models of the study:

    {
      "overall": {
        "<model>": {"hpwr": 55.1, "cf": 0.12, "ea": 3.4, "pc": 3.9, "joint": 0.31, "miou": 0.28,
                    "psnr": 18.2, "ssim": 0.61, "lpips": 0.32, "fvd": 410.0},
        ...
      },
      "by_edit_type": {
        "remove": {"<model>": {"hpwr": 52.0, "cf": 0.10, "ea": 3.1}, ...},
        "add": {...},
        "modify": {...}
      }
    }

hpwr is the Human Preference Win Rate of the same subset (human_preference_results.json written by
aggregate.py); the other entries are the per-model metric means. For every metric the script prints
Kendall tau-b and Spearman rho between the metric and HPWR across the models of "overall". LPIPS and
FVD are lower-is-better and are sign-flipped first. Per edit type, CF and EA are compared with the
HPWR of that subset over the same models. Metrics missing from the file are skipped.
"""
import itertools
import json
import math
import sys

# (key, label, sign): sign -1 for metrics where lower is better
METRICS = [("cf", "CF", 1), ("ea", "EA", 1), ("pc", "PC", 1), ("joint", "Joint", 1), ("miou", "Mask IoU", 1),
           ("psnr", "PSNR", 1), ("ssim", "SSIM", 1), ("lpips", "LPIPS", -1), ("fvd", "FVD", -1)]


def tau_b(x, y):
    nc = nd = tx = ty = 0
    for i, j in itertools.combinations(range(len(x)), 2):
        dx, dy = x[i] - x[j], y[i] - y[j]
        if dx == 0 and dy == 0:
            continue
        if dx == 0:
            tx += 1
        elif dy == 0:
            ty += 1
        elif dx * dy > 0:
            nc += 1
        else:
            nd += 1
    return (nc - nd) / math.sqrt((nc + nd + tx) * (nc + nd + ty))


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def rho(x, y):
    a, b = ranks(x), ranks(y)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    c = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    return c / math.sqrt(sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b))

# self-check on small examples with known values: tau-b 0.2 and rho 0.2 without ties, tau-b 5/sqrt(30) with one tie
assert abs(tau_b([1, 2, 3, 4, 5], [3, 4, 1, 2, 5]) - 0.2) < 1e-12 and abs(rho([1, 2, 3, 4, 5], [3, 4, 1, 2, 5]) - 0.2) < 1e-12
assert abs(tau_b([1, 2, 2, 3], [1, 3, 2, 4]) - 5 / math.sqrt(30)) < 1e-12


def corr(models, metric, human):
    x, y = [metric[m] for m in models], [human[m] for m in models]
    return {"tau_b": tau_b(x, y), "rho": rho(x, y), "n": len(models)}


def main():
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    overall = data["overall"]
    models = list(overall)
    print("%-10s %-9s %8s %8s %3s" % ("subset", "metric", "tau_b", "rho", "n"))
    human_all = {m: overall[m]["hpwr"] for m in models}
    for key, label, sign in METRICS:
        if all(key in overall[m] for m in models):
            a = corr(models, {m: sign * overall[m][key] for m in models}, human_all)
            print("%-10s %-9s %8.4f %8.4f %3d" % ("overall", label, a["tau_b"], a["rho"], a["n"]))
    for kind, values in data.get("by_edit_type", {}).items():
        hum = {m: values[m]["hpwr"] for m in values}
        for key, label in (("cf", "CF"), ("ea", "EA")):
            if all(key in values.get(m, {}) for m in models):
                a = corr(models, {m: values[m][key] for m in models}, hum)
                print("%-10s %-9s %8.4f %8.4f %3d" % (kind, label, a["tau_b"], a["rho"], a["n"]))


if __name__ == "__main__":
    main()
