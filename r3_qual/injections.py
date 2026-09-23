"""Pre-freeze QUAL injections applied inside Stage A fixture mode (non-science evidence only)."""
import json
import os
import shutil


def _raw(run, u):
    return os.path.join(run, "RAW_WORLD_%04d.json" % u)


def _hid(run, u):
    return os.path.join(run, "HIDDEN_TRUTH_%04d.json" % u)


def pre_freeze(name, run, units):
    u0, u1 = units[0], units[1]
    if name == "missing_world":
        os.remove(_raw(run, u1))
        os.remove(_hid(run, u1))
    elif name == "duplicate_world":
        w = json.load(open(_raw(run, u0)))
        w["unit"] = u1
        json.dump(w, open(_raw(run, u1), "w"), separators=(",", ":"))
        shutil.copyfile(_hid(run, u0), _hid(run, u1))
    elif name == "wrong_n_31":
        last = units[-1]
        os.remove(_raw(run, last))
        os.remove(_hid(run, last))
        for fn, key in (("EXECUTION_COUNTER.json", "units"), ("RUN_SUMMARY.json", "units_expected"), ("RUN_SUMMARY.json", "units_done")):
            p = os.path.join(run, fn)
            d = json.load(open(p))
            d[key] = [u for u in d[key] if u != last]
            json.dump(d, open(p, "w"), indent=1)
    else:
        raise KeyError(name)
