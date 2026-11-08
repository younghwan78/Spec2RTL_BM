"""Synthetic stand-in for site EDA tools. Output is not a measurement of anything."""
import sys

role = sys.argv[1]
if role == "fail":
    raise SystemExit(3)
if role == "synth":
    open("area.rpt", "w").write("Fixture report, no EDA executed\nTotal cell area: 1250.50\n")
    open("timing.rpt", "w").write("slack 1.0\n  data arrival time 0.900\n  data arrival time 2.500\n")
elif role == "power":
    open("power.rpt", "w").write("Dynamic Power: 1500.0 uW\nLeakage Power: 500.0 uW\n")
    open("activity.saif", "w").write("(FIXTURE activity for " + sys.argv[2] + ")\n")
elif role == "lint":
    open("lint.rpt", "w").write("Lint summary: 0 errors\n")
