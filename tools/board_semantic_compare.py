import sys, pcbnew
def mm(v): return round(pcbnew.ToMM(v), 4)
def dump(path):
    b = pcbnew.LoadBoard(path)
    out = []
    for fp in b.GetFootprints():
        p = fp.GetPosition()
        out.append(f"FP {fp.GetReference()} {fp.GetFPID().GetLibItemName()} {mm(p.x)} {mm(p.y)} {fp.GetOrientationDegrees():.1f}")
        for pad in fp.Pads():
            pp = pad.GetPosition()
            out.append(f"PAD {fp.GetReference()}.{pad.GetNumber()} {mm(pp.x)} {mm(pp.y)} {pad.GetNetname()}")
    for t in b.GetTracks():
        cls = t.GetClass()
        if cls == "PCB_VIA":
            p = t.GetPosition()
            out.append(f"VIA {mm(p.x)} {mm(p.y)} {t.GetNetname()} {mm(t.GetWidth(pcbnew.F_Cu))}")
        else:
            s, e = t.GetStart(), t.GetEnd()
            a, bb = sorted([(mm(s.x),mm(s.y)),(mm(e.x),mm(e.y))])
            out.append(f"TRK {t.GetLayerName()} {a} {bb} w={mm(t.GetWidth())} {t.GetNetname()}")
    for d in b.GetDrawings():
        if d.GetClass() == "PCB_TEXT":
            p = d.GetPosition()
            out.append(f"TXT {d.GetLayerName()} {d.GetText()!r} {mm(p.x)} {mm(p.y)}")
        elif d.GetClass() == "PCB_SHAPE":
            out.append(f"SHP {d.GetLayerName()} {d.ShowShape()} {d.GetStart()} {d.GetEnd()}")
    for z in b.Zones():
        out.append(f"ZONE {z.GetNetname()} layers={z.GetLayerName()} pts={z.Outline().TotalVertices()}")
    return sorted(out)
a, b2 = dump(sys.argv[1]), dump(sys.argv[2])
import difflib
same = a == b2
print("IDENTICAL" if same else "DIFFER")
if not same:
    for line in difflib.unified_diff(a, b2, lineterm="", n=0):
        print(line)
