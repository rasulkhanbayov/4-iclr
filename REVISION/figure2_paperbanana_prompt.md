# Figure 2 (pipeline): PaperBanana input

PaperBanana takes (1) a methodology text and (2) a caption describing what the
figure must communicate. Optional reference images can steer the style. Paste
block 1 as the methodology input and block 2 as the caption. Block 3 is style
guidance: append it to the caption, or use it as the Stylist instruction if your
version exposes one.

This figure shows the **revised** pipeline (decoupled scene/noise seeds and the
new validity checks). If the plan changes, update the labels in block 4 first.

---

## 1. Methodology text

PhysWeep measures whether an image-to-video generator realizes a requested
physical parameter. The pipeline has five stages, left to right.

(1) Request. A physical system (projectile, bouncing ball, inclined slide,
pendulum or spring-mass) and a requested parameter value θ, drawn from an
in-range set (values common in natural video) or an out-of-range set (rare
values). Two independent random seeds are also chosen: a scene seed s, which
sets the scene layout, and a noise seed z, which sets the generator's sampling
noise.

(2) Conditioning. A deterministic renderer draws the scene from s: a dark ball,
a floor, and the system's structure (a slope, a pendulum rod and pivot, or a
spring attached to a wall). The generator receives this conditioning frame
together with a text prompt that states θ (text channel), or several rendered
frames whose motion already implies θ (frame channel).

(3) Generator under audit. A frozen, off-the-shelf generator, treated as a black
box, produces a video continuation using noise seed z. It may be an open model
or a commercial API.

(4) Measurement. Two independent trackers (blob centroid and CoTracker3) follow
the ball. Each clip passes through validity checks: exactly one object in every
frame, stable object size, enough observed motion, agreement between the two
trackers, and a physics-fit quality R² ≥ 0.8. Clips that fail are labelled
invalid and counted, not silently dropped. Valid clips are fitted with the
system's closed-form law to recover θ̂.

(5) Analysis. θ̂ is compared with θ to give recovery error (PRE), faithfulness
slope β and extrapolation gap (EG). The out-of-range response is compared
against two failure shapes, prior reversion and case clamping. The variance of
θ̂ is split into three shares: how much is explained by the request θ, by the
scene seed s, and by the noise seed z.

A positive control runs ground-truth simulator video through the same
measurement stage and recovers θ exactly (slope 1.0001), showing the
measurement is correct when the physics is present.

## 2. Caption (communicative intent)

The PhysWeep measurement pipeline. A requested parameter θ, a scene seed s and a
noise seed z are chosen independently. The renderer draws the conditioning
scene from s, and the frozen generator produces a clip using z. Two trackers
and a set of validity checks decide whether the clip supports a measurement;
valid clips are fitted in closed form to recover θ̂. The analysis reports how
far θ̂ follows θ, and how much of θ̂'s variation is explained by the request,
the scene and the noise. A simulator positive control validates the
measurement path. Only the generator is untrusted; every other stage is
deterministic and label-free.

## 3. Style guidance

- Flat 2D vector diagram in the style of a CVPR or IJCV method figure. White
  background, thin dark-grey outlines, rounded rectangles, generous whitespace.
- **No** 3D icons, glossy gradients, drop shadows, padlocks, robots,
  magnifying glasses, film-strip clip-art or stock-icon look. Reviewers said
  the previous figure looked AI-generated; plain geometry avoids that.
- One horizontal row of five stage boxes connected by arrows. Width:height
  about 3:1, so it fits a full text width.
- Colour only to encode meaning, with at most 4 colours:
  - blue for the request θ and everything derived from it (θ, θ̂, β);
  - orange for the scene seed s;
  - purple for the noise seed z;
  - grey for neutral stages;
  - red outline only for the "invalid" output of the validity checks.
  The three seed and request colours must match the three bars of the
  variance-share plot in stage 5.
- Generator box: solid dark-grey box labelled "Frozen generator (black box)",
  with a small note "open model or API". Nothing visible inside the box.
- Drawings inside boxes stay schematic and minimal:
  - stage 2: a ball on a slope, drawn with lines only;
  - stage 3: three small video-frame rectangles;
  - stage 4: two thin trajectory lines (solid and dashed, one per tracker) and
    a small check list;
  - stage 5: a tiny scatter of θ̂ vs θ with a dashed identity line, plus three
    horizontal bars for the request / scene / noise shares.
- Positive control: a thin dashed green path below the main row, from a
  "Simulator video" box into stage 4, labelled "positive control: β = 1.0001".
- Sans-serif font (Helvetica or Arial look). Stage titles in bold sentence case,
  not ALL CAPS. Body labels at least as large as a 9 pt caption when printed
  at full text width.
- Do not add any text that is not in the label list below.

## 4. Exact labels (check spelling in the output; the last figure had "ideo")

Stage titles:
1. **Request**
2. **Conditioning**
3. **Frozen generator (black box)**
4. **Measurement**
5. **Analysis**

Labels inside or under the boxes:
- Stage 1: "system + parameter θ", "in-range / out-of-range", "scene seed s",
  "noise seed z"
- Stage 2: "renderer(s)", "text channel: prompt states θ", "frame channel:
  frames imply θ"
- Stage 3: "open model or API", "uses noise seed z", "generated video"
- Stage 4: "blob tracker", "CoTracker3", "validity checks:", "one object",
  "stable size", "enough motion", "trackers agree", "fit R² ≥ 0.8",
  "invalid → counted", "closed-form fit → θ̂"
- Stage 5: "PRE · slope β · EG", "prior reversion vs case clamping",
  "variance of θ̂: request / scene / noise"
- Bottom path: "Simulator video", "positive control: β = 1.0001"

## 5. Before you use the output

- Zoom to 200% and proofread every label against section 4.
- Check the colours match their meanings: blue = θ, orange = s, purple = z.
- Export as vector (PDF or SVG) if PaperBanana allows it. Otherwise export PNG
  at ≥ 300 dpi at full text width (≥ 2100 px wide). The last figure was only
  1327 px wide.
- Optional reference images: once the redesigned scenes exist (plan step 2), I
  can export one rendered conditioning frame per system to
  `REVISION/figures/refs/` for you to attach, so the stage-2 drawing matches the
  real stimuli.
