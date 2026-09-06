# Supervisor Meeting — 11 September 2026 (DRAFT, in preparation)

**Period**: 29 August (programme pivot) to 11 September 2026.
**Status of this file**: living draft. Points are added as they arise rather than
reconstructed on the day; anything unresolved by the meeting stays here as an open item.

---

## Headline

The cosmology programme is **design-complete and entering implementation**. Eight research
handoffs (H1–H8) ran between 29 August and 4 September, producing eleven design documents;
a coherence pass reconciled them, and a scientific review before dispatch
(`docs/cosmology/scientific_review.md`) confirmed the architecture holds at every rung. The
first implementation work is being delegated now.

**Settled since the last meeting:** the observable ladder's execution order
(`O0 → O1 → O2 → O4a → O3 → O4b/V`), the integration target (our own solver chained to
*unmodified* CAMB), the two-engine solver architecture, and the two-stage spectrum
architecture.

---

## 1. The question I most want your view on — does an FRW background solve the PGT field equations?

**Why it matters.** The whole spectator route rests on expanding the action about a
background and having the order-1 term vanish. That order-1 coefficient *is* the background
field equation, so it vanishes only if the background solves the equations of the theory
being expanded. We take CAMB's background, which solves **Einstein's** equations, while our
action is **PGT**. If a linear term survives, it is a **source** in the perturbation
equations — the spectator modes would be driven rather than freely propagating.

**What we already have.** The thesis settles the flat case:
`docs/tex/background_validity.tex` §"Background Torsion: `T̄ = 0` Is Exact" shows the Cartan
equation gives `0 = 0` for all PGT+EM theories with non-minimal couplings — **on flat
Minkowski with uniform `B₀`**. But the result it rests on (Bahamonde et al.) finds
non-trivial `T̄` precisely for **curved** spacetime, and FRW is curved.

**What we know on FRW.** From `2003.02690` (the group's own): `Q = 0` solves the
pseudoscalar torsion equation identically for *any* couplings — encouraging — but a *fully*
torsion-free FRW background additionally requires `σ₃ = 0` (k-screening) or the
Einstein–Cartan case. Outside those, theories sit in a tracking class whose effective
gravitational constant is rescaled, so CAMB's `G` is not the theory's `G`.

**Our provisional handling**, which I would like checked:

1. **Scope it.** Admissible theories are those admitting the assumed background — stated as
   an explicit validity condition of the route, with the theory judgement left to the user
   rather than silently assumed by the pipeline.
2. **Test it per theory, in-pipeline.** A background-EOM residual computed on the CAMB
   background. Because the residual *is* the tadpole coefficient, its tolerance is
   derivable rather than arbitrary: the induced source must sit far below the signal being
   computed. The expected regime is a **small new term on top of GR**, where residual and
   induced source are correspondingly small.
3. **Scope the extension as research, not resolve it now** — survey which theory classes
   provably admit a torsion-free FRW background and what settling it would require.

**Questions:** Is (1)+(2) the right posture, or does this need settling before O2? Is the
tracking class worth supporting, or is restricting to `T̄ = 0`-admitting theories the
cleaner scope? And is anyone aware of work extending the Minkowski argument to FRW?

**Where it bites first:** O4a (isotropic birefringence) *requires* a homogeneous torsion
mode `S₀(η) ≠ 0`, i.e. `T̄ ≠ 0` by construction — so it is the one rung guaranteed outside
the safe class.

---

## 2. Solver direction — WKB, as you expected

Confirming that the research supports the expectation from the last meeting, and reporting
one honest caveat.

**The design does what you recommended** — find the published methods for analogous
problems and rebuild them. The WKB rung is built on Lorenz–Jahnke–Lubich adiabatic Magnus,
lifted to first-order systems with non-normal `M`, cross-checked against Ioannisian–Smirnov
closed forms, with neutrino oscillation in matter (arXiv:0803.1967) as the template and
Handley's `oscode`/`riccati` as the scalar-case prior art.

**The prototype confirms the property that matters.** On a de Sitter adiabatic band at a
fixed 60 steps, the adiabatic stepper's error is *identical* for `k = 10, 100, 1000`, while
4th-order Magnus at the same step count is useless. That k-independence is the whole point.

**Caveat: no matrix RKWKB solver exists anywhere.** `oscode` and `riccati` solve *scalar*
second-order ODEs only. So this is a **generalization of a published scalar method to
matrix systems**, not a port — higher effort and higher risk than it may sound, and
independently publishable if it works.

**Decision taken:** WKB is implemented alongside Magnus in the first solver handoff rather
than deferred behind it. Both are measured; a bake-off decides composition and handover
thresholds on real numbers, with an adaptive RK baseline as the control. No candidate is
discounted on paper estimates.

**Question:** does treating the matrix generalization as a publishable result in its own
right match how you would want it framed?

---

## 3. For Wolfgang — the massless spectrum algorithm

Thank you for the steer that the massless analysis was left out of the supplementary
material **for convenience** (TorC not being interested in massless particles) rather than
because it is hard, and that the general algorithm is well understood.

That materially changes how we plan it: our design had recorded it as "implemented
numerically nowhere", which read as *we must invent it*. It is now scoped as
**find-and-implement** — locate the published treatments, curate them, and implement the
complete algorithm — the same pattern we are using for the Schur-complement criterion.

**Question:** which references do you have in mind for the general algorithm? That would
save us a literature search and, more importantly, make sure we implement the version you
would recognize as complete.

Related, and already acted on: we found that the released validator does **not** enforce
coupling-linearity (`NonLinearCouplings` is defined but never thrown, and a bare numeric
coefficient passes silently), so we are enforcing it on our side and treating that
validator as load-bearing for correctness.

---

## 4. The weakest link in the Gertsenshtein rung — the primordial magnetic field

O3 cannot be posed without an assumed background B-field, since the mixing is *linear* in
it. Two things concern me:

- **The assumption is worth ~10⁴ in the answer.** Published choices run from 47 pG to 5 nG,
  and `P ∝ B₀²`. Any bound we quote must carry its assumed field.
- **The backreaction question is unadjudicated.** Surveying the conversion literature, *not
  one* paper justifies neglecting the field's effect on the expansion history — each takes
  a fixed classical background and imports an observational upper bound. The one paper that
  engages the relevant bound (Caprini–Durrer anisotropic-stress limits) sets it aside on
  the strength of a published criticism. Our own justification is an **energy-density**
  argument (`r_B ≈ 10⁻⁷ B₋₉²`, hence `ΔN_eff ≲ 10⁻⁵`), which does not answer an
  *anisotropic-stress* bound.

**Question:** is the energy-density argument sufficient for our purposes, or should we
adjudicate the anisotropic-stress bound before quoting any O3 result? Currently flagged as
must-resolve-before-publication.

---

## 5. Status, briefly

- **Design documents:** eleven, under `docs/cosmology/`, with `docs/COSMOLOGY_PROGRAM.md`
  as the operational record (decisions register, ladder, workstreams, wave board).
- **Package:** `tidalcosmo/` scaffold beside legacy `tidal/`, strangler-fig migration; new
  code never imports legacy, test-enforced.
- **First implementation wave:** packaging and extras; freezing the legacy oracle as
  committed data before any porting; installing PSALTer and passing its install gate.
- **Approach to delegation:** self-contained handoff prompts to separate sessions, each
  with quantitative success criteria stated before code, merged centrally against a
  checklist.

---

## Open items carried in

- The `ν⁰` vs `ν²` frequency scaling is **per-operator**, not a single number. Only `n = 0`
  operators can *explain* the 4.8σ birefringence signal; `ν²` operators can only be
  bounded. Derivation in progress.
- The Chern–Simons couplings need **bare `A_μ`** handling, which the pipeline does not yet
  support — an unsolved problem rather than a configuration step.
- Licensing for code derived from the PSALTer/supplementary sources: a release gate, not an
  implementation one. Attribution to be settled at publication.
