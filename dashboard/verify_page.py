"""Assert the rendered page carries the claims its artifacts support.

The build passing proves the page compiles, not that it says anything. A
lookup regression removed the three headline reads under the baselines chart
and produced no error at all — TypeScript was satisfied, the build was clean,
and the section was simply gone. This checks the rendered text against
data.json, which is the only thing that would have caught it.
"""
import json, sys, urllib.request


def inr(n: float) -> str:
    """Indian digit grouping, the way the page formats money.

    The page uses toLocaleString("en-IN"), which renders 272281 as 2,72,281 —
    lakh grouping, correct for an Indian payments product. Python's ',' format
    gives 272,281. Checking with the wrong convention made this script report
    the page as missing its own headline twice in a row; the page was right
    both times.
    """
    s, neg = f"{abs(int(round(n)))}", n < 0
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if neg else "") + s
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5175/"
d = json.loads(urllib.request.urlopen(URL + "data.json").read())

pol = {p["policy"]: p for p in d["baselines"]["policies"]}
ours, blast, rand = pol["ev_policy_lookahead"], pol["blast_everyone"], pol["random_targeting"]
inc = lambda p: p["incremental_per_1000_cases"]["point"]
fair, dnd = d["fairness"], d["dnd_signal"]
scat = fair["scatter_sample"]
harmful = [p for p in scat if p["tau_true"] < 0]
spared = round((1 - sum(p["contacted"] for p in harmful) / len(harmful)) * 100)

expected = {
    f"{inc(ours) / inc(rand):.2f}x": "baselines: ratio vs random",
    f"{round((1 - ours['contacts_sent'] / blast['contacts_sent']) * 100)}%": "baselines: fewer contacts",
    f"{dnd['ratio']:.2f}x": "N2: corrected do-not-disturb ratio",
    f"{spared}%": "quadrant: do-not-disturbs spared",
    # The headline comes from run_batch (results.json), NOT from the baselines
    # table — different experiment, different eval seed, different number.
    # Checking the baselines figure here was an error in this script, not on
    # the page: it expected ₹300,677 where the page correctly says ₹272,281.
    f"₹{inr(d['batch']['incremental_per_1000_cases']['point'])}": "headline incremental (run_batch)",
    f"{d['calibration']['verdict']['mean_calibration_slope']:.3f} mean": "calibration: slope",
    f"₹{inr(d['regret']['totals']['net'])}": "regret: net",
}
required_sections = {
    ".rl-subtraction": "subtraction", ".rl-chart svg": "baselines chart",
    ".rl-frontier-reads": "baselines reads", ".rl-quad svg": "uplift quadrant",
    ".rl-curve svg": "caution curve", ".rl-scissor svg": "decile scissor", ".rl-audit-card": "audit cards",
    ".rl-kernel": "kernel", ".rl-livesection": "live console", ".rl-explorer": "explorer",
    ".rl-regret": "regret ledger",
}

fails = []
with sync_playwright() as p:
    for mode, args in [("gl", ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]),
                       ("nogl", ["--disable-webgl", "--disable-gpu", "--disable-3d-apis"])]:
        b = p.chromium.launch(headless=True, args=args)
        pg = b.new_page(viewport={"width": 1512, "height": 950})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        pg.on("console", lambda m: errs.append("console: " + m.text[:110]) if m.type == "error" else None)
        pg.goto(URL, wait_until="networkidle"); pg.wait_for_timeout(2500)
        for sel, name in required_sections.items():
            if pg.locator(sel).count() == 0:
                fails.append(f"[{mode}] section missing: {name} ({sel})")
        body = pg.locator("body").inner_text()
        for text, why in expected.items():
            if text not in body:
                fails.append(f"[{mode}] artifact says {text!r} ({why}) but the page does not")
        if errs:
            fails.append(f"[{mode}] console/page errors: {errs[:3]}")
        b.close()

print("\n".join(fails) if fails else f"OK — {len(required_sections)} sections and "
      f"{len(expected)} artifact-backed claims render on both paths")
sys.exit(1 if fails else 0)
