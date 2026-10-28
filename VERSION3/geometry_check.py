import pymupdf, itertools, sys

def segs_from_page(pg, clip=None):
    """Extract actual stroked line segments (not bboxes) from the page."""
    out=[]
    for p in pg.get_drawings():
        if p.get("stroke") is None and p.get("type")=="f":   # pure fill, skip
            continue
        for it in p["items"]:
            if it[0]=="l":
                a,b=it[1],it[2]; out.append((a.x,a.y,b.x,b.y))
            elif it[0]=="re":
                r=it[1]
                out += [(r.x0,r.y0,r.x1,r.y0),(r.x1,r.y0,r.x1,r.y1),
                        (r.x1,r.y1,r.x0,r.y1),(r.x0,r.y1,r.x0,r.y0)]
            elif it[0]=="c":
                pts=[it[1],it[2],it[3],it[4]]
                for u,v in zip(pts,pts[1:]): out.append((u.x,u.y,v.x,v.y))
    if clip:
        out=[s for s in out if clip.intersects(pymupdf.Rect(min(s[0],s[2]),min(s[1],s[3]),
                                                            max(s[0],s[2])+.01,max(s[1],s[3])+.01))]
    return out

def seg_hits_rect(seg, r):
    """Liang-Barsky segment vs rectangle."""
    x0,y0,x1,y1=seg; dx,dy=x1-x0,y1-y0
    t0,t1=0.0,1.0
    for p,q in ((-dx,x0-r.x0),(dx,r.x1-x0),(-dy,y0-r.y0),(dy,r.y1-y0)):
        if p==0:
            if q<0: return False
        else:
            t=q/p
            if p<0:
                if t>t1: return False
                if t>t0: t0=t
            else:
                if t<t0: return False
                if t<t1: t1=t
    return True

def audit(pdf, page, clip, label):
    d=pymupdf.open(pdf); pg=d[page]
    spans=[]
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines",[]):
            for x in l["spans"]:
                t=x["text"].strip(); r=pymupdf.Rect(x["bbox"])
                if t and (clip is None or (clip.contains(r.tl) and clip.contains(r.br))):
                    spans.append((r,t))
    tt=0
    for (r1,t1),(r2,t2) in itertools.combinations(spans,2):
        i=r1&r2
        if i.is_empty or i.get_area()<2: continue
        if t1 in t2 or t2 in t1: continue
        if any(c in "ˆ˜¯˙¨´`^~" for c in t1+t2): continue
        if i.get_area()/min(r1.get_area(),r2.get_area())>0.25:
            print(f"  TEXT-ON-TEXT {t1[:20]!r} <-> {t2[:20]!r}"); tt+=1
    segs=segs_from_page(pg, clip)
    tl=0
    for r,t in spans:
        if len(t)<2: continue
        core=pymupdf.Rect(r.x0+1.0,r.y0+1.0,r.x1-1.0,r.y1-1.0)
        if core.is_empty or core.width<=0 or core.height<=0: continue
        n=sum(1 for s in segs if seg_hits_rect(s,core))
        if n: print(f"  TEXT-ON-LINE {t[:34]!r} crossed by {n} segment(s)"); tl+=1
    print(f"{label}: {len(spans)} spans, {len(segs)} segments -> text-on-text {tt}, text-on-line {tl}")
    return tt,tl
