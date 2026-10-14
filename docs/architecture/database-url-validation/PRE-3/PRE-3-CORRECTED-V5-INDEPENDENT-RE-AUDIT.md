# WO-PRE-3-V5-INDEPENDENT-RE-AUDIT — INDEPENDENT READ-ONLY RE-AUDIT OF PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V5.md

**Verdict:** `ACCEPTED`
**Audit type:** strict read-only, independent, adversarial. No code, no guard, no test, no repository operation, no Git command, no publication, no deployment, no authorization.
**Authority for this audit:** WO-PRE-3-V5-INDEPENDENT-RE-AUDIT, sections 1–14 only.
**All figures below were measured live by this pass from the stored bytes.** No figure is copied from V5, from the V4 audit, or from the V5 creation report without an independent measurement. Where a value is inherited rather than re-derived, it is labelled as such.

---

## 0. BOTTOM LINE

`PRE3_V5_INDEPENDENT_RE_AUDIT_VERDICT = ACCEPTED`

**All three findings of the V4 independent audit — `F-4A`, `F-4B`, `F-4C` — are resolved correctly, completely, and with no undeclared collateral change.** V4 is preserved exactly as declared: a deterministic whole-body alignment of the frozen V4 file against V5's Part II region returns **exactly five non-equal hunks, one per declared §22.3 anchor, with no residue**, and the declared line arithmetic (**2673 → 2691, net +18**) reproduces exactly, hunk for hunk. V5's identity, its series-convention digest and its non-embedding of its own stored digest all reproduce independently. The authorization boundary is intact at every layer.

**Why `ACCEPTED` and not `ACCEPTED WITH CONDITIONS`:** the verdict scale allows `ACCEPTED` only where all material claims reproduce and no correction is required. Every material claim in V5 that lies within this pass's authorized evidence scope reproduces from fresh measurement, and no correction is required of V5. The one residual defect found in this round is **not in V5**: the digest literal for the V4-audit input as *delivered to this pass in §1.3 of the work order itself* is again 63 hexadecimal characters (the DV-0 pattern repeated). That is a work-order / delivery-channel defect; it is recorded below as **ADV-1** and it does **not** undermine the identity of the V5 input (identity is established by exact byte count plus an all-but-one-character digest match). It is an advisory on the work order, not a condition on the audited artifact.

**Why not `PARTIALLY VERIFIED`:** nothing material failed to reproduce. Identity (all three inputs), the series digest and its selector uniqueness, the V4→V5 alignment and its exact five-hunk structure, the declared arithmetic, all three required corrections, the anchoring of the eleven historical V4 anchors as a separate accounting, the D-1…D-4 open statuses and the non-permissive authorization boundary were each independently reproduced.

**Why not `REJECTED`:** no material claim is substantively false and no control is unsafe. No permissive grant exists anywhere in V5; no operator decision is selected or implied.

**Why not `BLOCKED`:** all three inputs exist, are readable, and were identified by measured bytes before use.

---

## 1. IDENTITY AND INTEGRITY (§4 of the work order)

### 1.1 Measured from the stored bytes, before reading content

| Input | Exact path | Bytes measured | Bytes expected | Result | SHA-256 measured | SHA-256 expected | Result |
|---|---|---|---|---|---|---|---|
| **V5 target** | `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V5.md` | **270195** | 270195 | **MATCH** | `d33f990715f6fb5563217f1c1664dc3be2bc1ff55ade5a04d1483bddeb39d6b3` | same | **MATCH** |
| **V4 predecessor** | `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V4.md` | **230449** | 230449 | **MATCH** | `694ea3b62c6a1fb96da042f5d30fb0174db2ec47dd78f9e9cf89584677ec27fb` | same | **MATCH** |
| **V4 audit** | `/opt/data/output/PRE-3-CORRECTED-V4-INDEPENDENT-RE-AUDIT.md` | **43766** | 43766 | **MATCH** | `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0` (64 hex chars) | see §7 (DV-0) | **MATCH to measured bytes** |

Byte counts were obtained with `os.path.getsize`-equivalent reads and full-file `hashlib.sha256` over the exact bytes; no rendering, no normalisation.

### 1.2 Line endings, final newline, truncation

- V5: **LF only** — 0 occurrences of `CR LF`, 0 bare `CR`. Terminates with a single LF. No NUL byte anywhere. Split on LF yields 3083 elements, the last being empty → **3082 content lines**.
- V5 is **not truncated**: its final content line (line 3082) is the mandated terminal boundary line (see §8).
- V4: LF only, single trailing LF, 2673 content lines. V4 audit: LF only, single trailing LF, 402 content lines.
- Both figures (2673, 402) match V5's own statements at §I.2 (lines 50–51) and §I.6 (lines 121–124).

### 1.3 Does V5 embed its own stored-file digest?

**No.** The substring `d33f9907` (the first eight hex characters of V5's stored digest) occurs **0 times** in V5. The file therefore cannot contain its own digest, and §22.5's statement that the stored digest is "reported in the terminal response … and is NOT embedded here" is **true as measured**.

**Does V5 clearly distinguish stored-file SHA-256 from the series digest?** **Yes**, at §22.5 lines 2959–2972: the stored-file digest bullet states the read-back was performed by the pass on its own output and that "no independent verification of the stored-file digest is claimed here"; the series-convention bullet then states the rule and explicitly says "It is **not** the SHA-256 of the bytes on disk". The two are never conflated, and the series digest is never presented as a file-integrity value.

### 1.4 Output path availability

The designated output path `/opt/data/output/PRE-3-CORRECTED-V5-INDEPENDENT-RE-AUDIT.md` **did not exist** before this report was written (checked before writing). No collision. Nothing was overwritten. No substitute path was used.

---

## 2. SERIES DIGEST (§5 of the work order)

**The rule was re-implemented mechanically from the rule text and executed. The reported value was not trusted.**

Rule as claimed by V5 (§22.5 lines 2963–2970) and by the work order §5: locate the unique line beginning with the literal `- **V5 SHA-256` and ending with `-hex field zeroed):**`; read the single 64-hex token on the immediately following line; replace those 64 characters with `0`; SHA-256 the whole resulting file.

Measured:

- **Selector uniqueness: exactly one line.** One and only one line begins with `- **V5 SHA-256`: line **2971** (0-based index 2970), byte-for-byte `- **V5 SHA-256 (series convention — the designated 64-hex field zeroed):**`. It also ends with the required terminator.
- **The following line (2972)** carries **exactly one** token of 64 hexadecimal characters: `66a76cdbd57a704ac69245fff8a373d57741ecee80f65ed6ecb9f40c73eaef51`. A regex requiring ≥32 hex characters finds exactly one match on that line, length 64.
- **Substitution is length-preserving:** the token occurs **once** in the file; replacing it with 64 zeros leaves the file at **270195** bytes — unchanged.
- **Result:** SHA-256 of the zeroed file = `66a76cdbd57a704ac69245fff8a373d57741ecee80f65ed6ecb9f40c73eaef51`.
- **Declared value:** `66a76cdbd57a704ac69245fff8a373d57741ecee80f65ed6ecb9f40c73eaef51`. **REPRODUCED EXACTLY.**

**Selector does not capture the carried labels.** The three carried labels present in V5 are:
- `- **V4 SHA-256 …` at line **2783** (token on 2784: `ad403ab0cd668aedc1bf9ef4f7dc4b02a04100c5c26001b2ea3611b304d13443`);
- `- **V3 SHA-256 …` at line **2588** (token on 2589: `e748e8b80334a208086bd508c93a33f37cbdf3df0d03a45528064e2422d42efc`);
- `- **SHA-256 …` (unversioned, the carried V2 label) at line **2284** (token on 2285: `a96ee5c47470a6af3b8d9df10b49720082dbf063ca73536db2e260e23ed63a19`).

None begins with `- **V5 SHA-256`, so none is selectable by the rule. This confirms V5's own §22.5 statement (line 2970) and the Part II banner (line 166).

**Cross-check of the carried values against their own files (not against the carried copy).**
- V4's own label is at V4 line 2601 (token on 2602). Applying the same zero-and-hash procedure to **V4's own bytes** returns `ad403ab0cd668aedc1bf9ef4f7dc4b02a04100c5c26001b2ea3611b304d13443` — identical to the value V5 carries.
- V2's and V3's carried values are the values their own passes documented; this pass did not re-derive them from V2/V3 (see §9, inherited claims).

**Materiality of ambiguity:** none. The rule selects exactly one line, that line has exactly one candidate token, the substitution is length-preserving, and the digest reproduces. The series digest is reported **separately** from the stored-file SHA-256 throughout this report.

---

## 3. V4 PRESERVATION AND V5 CHANGE ACCOUNTING (§6 of the work order)

### 3.1 V4 unchanged

V4 measured at **230449 bytes / `694ea3b6…ec27fb`** — identical to §1.2 of the work order, identical to V5 §I.2 line 34 and §I.3 line 63, and identical after this audit's own report was written (§12). **MATCH.** V4 was not modified by V5 and was not modified by this audit.

### 3.2 V5 identifies V4 as its predecessor

Yes: V5 line 8 (`**Supersedes (as design guidance):** PRE-3 V4`), §I.2 (lines 30–57), §I.4 (lines 82–87), and §22.3 (lines 2912–2915). V5's Part II heading (line 155) is `## Part II — Carried-forward V4 body`.

### 3.3 Alignment method (deterministic, no normalisation)

- V4 content lines: `open(V4,'rb').read().decode('utf-8').split("\n")[:-1]` → **2673 lines**.
- V5 Part II region: V5 lines **169–2859** inclusive → **2691 lines**. Boundaries verified by content, not by assumption: V5 line 169 is byte-equal to V4 line 1 (`# PRE-3-CORRECTED-V4 — DESIGN CORRECTION AND RECONCILIATION (FOURTH BOUNDED CORRECTION PASS)`) and V5 line 2859 is byte-equal to V4 line 2673 (the closing italic line of V4's §21.7 footer). V5 line 155 is the `## Part II — Carried-forward V4 body` heading, 156 is blank, 157–167 is the V5 disambiguation banner, 168 is blank, 2860 is blank, 2861 is `## Part III — V5 corrections, change log and integrity record`.
- Comparison: `difflib.SequenceMatcher(None, V4_lines, V5_PartII_lines, autojunk=False)` — exactly the method V5 declares at §22.3 lines 2909–2910. No normalisation, no line ending translation, no whitespace folding, no exclusions.

**Result:** ratio **0.9910514541387024**; **exactly 5 non-equal hunks**.

### 3.4 The five hunks — exhaustive, with no residue

| # | V4 own lines | V5 lines | Length | Δ | Declared anchor (V5 §22.3) | Finding |
|---|---|---|---|---|---|---|
| 1 | 74–77 | 242–250 | 4 → 9 | +5 | anchor 2 — §I.4 paragraph | F-4B / C-4-2 |
| 2 | 2510 | 2683 | 1 → 1 | +0 | anchor 5 — §21.1 `C-V3-3` requirement cell (optional advisory) | optional advisory |
| 3 | 2516–2518 | 2689–2695 | 3 → 7 | +4 | anchor 3 — §21.1 paragraph | F-4B / C-4-2 |
| 4 | 2571–2572 | 2748–2754 | 2 → 7 | +5 | anchor 1 — §21.3 additions note | F-4A / C-4-1 |
| 5 | 2626–2630 | 2808–2816 | 5 → 9 | +4 | anchor 4 — §21.6 DV-6 bullet | F-4C / C-4-3 |

Every hunk is a declared anchor; every declared anchor is a hunk; **no undeclared residue of any kind** — no stray line inserted, deleted or altered outside these five ranges. The V4 line numbers in §22.3 are V4's **own** numbering, and each of the five ranges above matches §22.3 exactly.

### 3.5 Declared arithmetic reproduces exactly

2673 content lines + (9−4) + (1−1) + (7−3) + (7−2) + (9−5) = 2673 + 5 + 0 + 4 + 5 + 4 = **2691**. V5 §22.3 states the per-anchor deltas as, in anchor order, +5 (anchor 1), +5 (anchor 2), +4 (anchor 3), +4 (anchor 4), +0 (anchor 5), net +18, with the explicit sum `2673 + 5 + 5 + 4 + 4 + 0 = 2691` (lines 2925–2927). **Verified hunk-for-hunk; the arithmetic and the per-anchor deltas are correct, and the gross Part II length is 2691.**

### 3.6 The historical eleven anchors remain a separate accounting

- V4's §21.3 table — "Exact anchors changed in Part II (eleven)" — occupies V4 lines 2548–2566 and lies **wholly inside an equal region** of the alignment. In V5's Part II it is therefore **byte-identical** to V4's version, and V5 §22.2 row 6 (line 2898) claims exactly this.
- V5 §22.3 lines 2912–2915 state that the five V5 anchors "are NOT part of V4's historical eleven anchors", that §21.3 accounts for V4→V3 and §22.3 for V5→V4, and that the two accountings are separate.
- V5 §22.3 line 2937–2938 states: "**V5 does not claim that any of its edits were part of V4's original eleven anchors.**" **No statement anywhere in V5 claims a V5 edit to be one of the eleven.** Verified by search: the only rows that mention "eleven" are the §22.1 row 2 requirement/basis, §I.4 line 97, §22.3 lines 2912–2914 and the carried §21.3 heading — all of which keep the sets distinct.
- Independent check of the eleven anchors' own semantics (against V4's §21.3 table read from V4's bytes): anchor 1 = V3 line 137 deleted (duplicate title); anchors 2 (V3 line 830, §5.25 row) and 3 (V3 lines 850–852, §5.25 point 3) = the C-V3-1 narrative; anchor 4 = V3 line 866 (F-V6 markup); anchor 5 = V3 lines 1773–1774 (**§15 provenance note**, F-V8); anchor 6 = V3 line 1908 (§16.6 G10, F-V7); anchors 7 (V3 line 2173, with a new row 7a) and 8 (V3 line 2174) = §20.2 items; anchors 9/10 = V3 lines 2205/2211 (§20.3 rows 11/17, F-V5); anchor 11 = V3 line 2218 (§20.3 additions note). This independently confirms the anchor identities that V5's F-4B correction cites (see §5 below).

### 3.7 Item-by-item answer to the work order's §6 checklist

1. V4 unchanged — **CONFIRMED** (§3.1).
2. V5 names V4 its predecessor — **CONFIRMED** (§3.2).
3. Part II alignable against complete V4 content deterministically — **CONFIRMED** (§3.3).
4. Exactly five declared non-equal hunks, no undeclared residue — **CONFIRMED** (§3.4).
5. Declared arithmetic 2673 → 2691, net +18 — **CONFIRMED** (§3.5).
6. The historical eleven remain distinct from the five — **CONFIRMED** (§3.6).
7. V5 claims no V5 edit belonged to the eleven — **CONFIRMED** (§3.6).
8. The optional `C-V3-3` quotation annotation alters neither the quoted requirement nor the resolution — **CONFIRMED**; see §6.
9. Earlier findings/dispositions retained as historical or inherited, not silently upgraded — **CONFIRMED**; see §5, §6 and §9.

---

## 4. REQUIRED FINDING F-4A / C-4-1 (§7 of the work order) — RESOLVED

**Where the correction lives:** V5 §22.1 row 1 (line 2871); V5 §22.3 anchor 1 (line 2919); and the corrected V4 §21.3 additions note carried in Part II at **V5 lines 2748–2754** (the hunk at V4 lines 2571–2572). V5 likewise names its *own* new header block at §22.3 lines 2933–2938.

**Measured content of the corrected passage (V5 2748–2754):** it names "V4's own **header block** (V4's own line numbering, lines **1–16**: title line 1; cover metadata lines 3–9 — document type, work order, mode, repository, branch, supersedes and new-artifact; and the three **authorization-gate lines 13–15**)", then preserves the §21.7 reference ("§21.7 refers to the gates stated at the head of this document, so no gate is hidden"), then states the gates are "**restrictive controls** (`NOT GRANTED`); they do **not** authorise implementation and imply no permission of any kind", and closes with the `AUDIT-DRIVEN CORRECTION (V5) — F-4A` marker.

**Verified against V4's actual bytes** (V4 lines 1–16 read from V4):
- line 1 is the V4 title;
- lines 3–9 are exactly seven cover-metadata lines: document type, work order, mode, repository, branch, supersedes, new-artifact;
- lines 13–15 are the three authorization gates, each `NOT GRANTED`, each carrying **exactly 4 asterisks** (2 + 2, balanced) by `str.count` — byte-verified, see §8.3.

**Verified against the document's own reference chain:** V4's §21.7, carried at V5 lines 2824–2831, does say "The gates stated at the head of this document, and repeated immediately below, are unchanged and remain **NOT GRANTED**"; and the Part II banner (V5 lines 157–167) fixes the referent of "this document"/"this pass" inside Part II to the V4 authoring gate. The F-4A correction's explanation of that reference is therefore accurate.

**Work order §7 requirements, element by element:**
- explicitly accounts for V4 lines 1–16 — **YES**;
- identifies the title, cover metadata, and the authorization-gate lines 13–15 — **YES**;
- preserves the explanation that §21.7 references the gates at the head of the document — **YES**;
- clearly states the gates are restrictive and do not authorize implementation — **YES**;
- does not imply the new inventory retroactively formed part of V4's original eleven anchors — **YES** (the additions note is a V4-relative inventory; §22.3 lines 2912–2915 and 2937–2938 keep the two accountings separate).

**F-4A / C-4-1: RESOLVED, correctly and completely.** No residual gap: the corrected note now covers every part of V4's header block at the same granularity the finding required (title line, the seven cover-metadata lines, the three gate lines), plus the §21.7 reference and the restrictiveness statement.

**Note on scope of the same correction for V5 itself:** V5 applies the analogous disclosure to its own header block at §22.3 lines 2933–2938 ("V5's own **header block** (this file, lines **1–16**: title line 1; cover metadata lines 3–9; and the three **authorization-gate lines 13–15**)"), verified against V5's actual lines 1–16: line 1 title, lines 3–9 the seven metadata lines, lines 13–15 the gates. **No F-4A-equivalent gap exists in V5's own accounting.**

---

## 5. REQUIRED FINDING F-4B / C-4-2 (§8 of the work order) — RESOLVED

**Where the correction lives:** V5 §22.1 row 2 (line 2872); V5 §22.3 anchors 2 and 3 (lines 2920–2921); the corrected V4 §I.4 paragraph in Part II at **V5 lines 242–250** (hunk at V4 74–77); the corrected V4 §21.1 paragraph in Part II at **V5 lines 2689–2695** (hunk at V4 2516–2518); and V5's own restatement at §I.4 lines 94–99, §22.1 lines 2876–2879.

**What V4 said (the defect):** §I.4 (V4 74–77) said the V3 dispositions of `C-V2-1`, `C-V2-2`, `C-V2-3` and advisories `NV-2`, `NV-4`, `NV-5`, `NV-6`, `NV-7` were "carried in Part II **unchanged**"; §21.1 (V4 2516–2518) said the same statuses were "carried in Part II with the statuses V3 gave them".

**What V5 now says (measured):**
- Part II §I.4 (V5 242–250): heading changed to "**Preserved without re-grading — statuses carried forward, prose not byte-identical (explicitly).**"; the statuses are carried "with the **statuses V3 gave them, unchanged**" while "**the explanatory prose is not carried byte-identically**"; it names "Five of the eleven declared anchors of §21.3 — anchors 2, 3, 7 and 8 (inside the `C-V2-1` narrative at §5.25 and §20.2) and anchor 5 (the §15 provenance note inserted under `C-V2-2` / `NV-7`)"; it bounds the prose changes to "**only to the explicitly declared V4 anchors** of §21.3"; it retains V4's original "makes no new claim … does not re-grade them" and the `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` sentence verbatim; and it carries the `AUDIT-DRIVEN CORRECTION (V5) — F-4B` marker.
- Part II §21.1 (V5 2689–2695): same substance, naming the same anchors and the same bound, with the F-4B marker.
- V5's own §I.4 (lines 94–99) restates it for V5's own predecessor relationship, adding that the prose is subject to V4's §21.3 anchors **and** V5's own §22.3 anchors.

**Independent check of the anchor references (read from V4's §21.3 table, V4 lines 2548–2566):** anchors 2 (V3 line 830) and 3 (V3 lines 850–852) are the §5.25 `C-V3-1` narrative; anchors 7 (V3 line 2173) and 8 (V3 line 2174) are the §20.2 items; anchor 5 (V3 lines 1773–1774) is the §15 provenance note (F-V8). The corrected wording's anchor set {2, 3, 7, 8} and {5} and its §5.25 / §20.2 / §15 locations are therefore **accurate against V4's own accounting** — and the V4 audit's own finding F-4B used the same set and locations, so V5's statement that this is "inherited, not re-derived here" (§22.1 line 2872) is correctly labelled.

**Does the correction silently change any finding, severity, disposition, evidence claim, or the scope of V4's eleven anchors?** **No.**
- V4's §21.3 eleven-anchor table is byte-identical in Part II (inside an equal region; §3.6).
- The replaced paragraphs retain V4's substantive assertions verbatim — "V4 makes no new claim about them and does not re-grade them" and "The `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` status of every design item is likewise unchanged" survive in both corrected paragraphs.
- No status is upgraded or downgraded: V5 §22.1 lines 2876–2879 and §I.4 lines 98–99 say so and specify no re-grading.
- The correction *narrows* a byte-preservation claim; it does not weaken any control, and it does not touch D-1…D-4.

**F-4B / C-4-2: RESOLVED, correctly and completely.**

---

## 6. REQUIRED FINDING F-4C / C-4-3 (§9 of the work order) — RESOLVED

**Where the correction lives:** V5 §22.1 row 3 (line 2873); V5 §22.3 anchor 4 (line 2922); the corrected V4 §21.6 DV-6 bullet in Part II at **V5 lines 2808–2816** (hunk at V4 2626–2630); and V5's own DV-6 at §22.6 lines **3005–3017**; with the author-session labelling also at §22.6 DV-9 (lines 3023–3025).

**Measured content — Part II (V5 2808–2816):** the heading is now "**DV-6 (no failed operation reached any artifact). — `AUDIT-DRIVEN CORRECTION (V5)` — F-4C:**"; the text records that "the original heading read \"no failed operations\" and contradicted the `NameError` disclosed below; it is corrected here to this narrower, accurate claim"; it then asserts only "**No failure of this gate reached any artifact.** No operation whose result reached an artifact failed…" and preserves the protected-path statement; the parenthetical preserves the `NameError` disclosure (the initial attempt to compute the upstream identities failed with a `NameError` in the pass's own throwaway script; corrected and re-run within the same pass; no artifact affected) and labels it "an **author-session claim** of this gate [that] was not independently re-observed".

**Measured content — V5's own §22.6 DV-6 (V5 3005–3017):** same corrected heading; discloses, "rather than concealed, exactly as finding F-4C requires": (i) `DV-0`, the malformed expected V4-audit digest, an input-side anomaly; (ii) one pre-write validation run of the pass's own throwaway builder that exited early because the expected V4-audit digest had been mis-typed inside that builder; (iii) a later run of the same builder that stopped on a mis-specified internal assertion. It states (ii) and (iii) were corrected within the same pass **before any file was written**, that no artifact was affected, and that those corrections "are author-session claims of this pass and were not independently re-observed"; it also records V4's own §21.6 DV-6 defect as inherited.

**Work order §9 requirements, element by element:**
- the heading no longer contradicts the disclosed `NameError` — **YES**; the heading is now "no failed operation reached any artifact", and the bullet says no *failure that reached an artifact* occurred;
- the `NameError`, its correction and its rerun remain disclosed — **YES**, preserved in Part II and re-recorded in §22.6;
- the claim that no deliverable artifact was affected is appropriately bounded — **YES**: "No failure of this gate reached any artifact" / "No operation whose result reached an artifact failed" / "no artifact was affected" — all scoped to artifacts, not an absolute claim that nothing failed;
- author-session claims are not falsely presented as independently observed — **YES**: the correction is labelled "an **author-session claim** … not independently re-observed" in Part II, and DV-9 (3023–3025) says the same of the inherited items; the V5 pass claims no independent re-observation;
- no historical deviation is concealed or relabelled as though it never occurred — **YES**: the superseded heading is quoted and named, and the non-material failures are disclosed in *both* the V4-and-correction bullet and V5's own deviation register. The correction **adds** disclosure (items (ii) and (iii) were not in V4's disclosure) rather than removing any.

**F-4C / C-4-3: RESOLVED, correctly and completely.** No defect remains of the kind F-4C described: no heading in V5's deviation registers contradicts its own content.

---

## 7. INPUT ANOMALY DV-0 (§10 of the work order)

### 7.1 The corrected expected digest — length check

The measured SHA-256 of `/opt/data/output/PRE-3-CORRECTED-V4-INDEPENDENT-RE-AUDIT.md` is **`65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0`**, which is **exactly 64 hexadecimal characters** (asserted programmatically: `len == 64`).

### 7.2 The expected literal **as delivered to this pass in §1.3 of this work order**

The literal that arrived in §1.3 of this work order is **63 characters**:

`65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbea1a2c675f0`

It equals the measured digest **with exactly one character deleted**: the hex character `2` at **1-based position 54** (0-based index 53). `difflib` on the two strings returns one `delete` opcode at index 53 and full equality either side. **This is the identical DV-0 pattern.**

**Recorded explicitly, as required:**
- **Original mistake:** the historical expected value for the V4-audit input was stated as **63 hex characters** — one character short of a valid SHA-256 — the missing character being `2` at position 54.
- **Corrected value:** the 64-character digest actually measured from the file is `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0`.
- **The malformed historical value is NOT treated as a valid SHA-256 anywhere in this audit.**
- **The corrected value is documented inside V5 itself** — at §I.2 line 35 (second column), §I.2 line 40, §I.3 line 64 and §22.6 line 2983 — so the substance of the work order's §1.3 claim ("the corrected 64-character digest reported as measured by the V5 creation pass") is verifiable from V5's own bytes, even though the literal *delivered to this pass* is short.

**Arithmetic and positional consistency of the creation pass's account:** V5 §I.2 lines 37–46 and §22.6 lines 2979–2985 say the stated value is 63 hex characters and "equals that measured value with **exactly one character deleted** (position 54, hex `2`)". Both halves were checked independently: the count is 63, the deletion position is 54, and the deleted character is `2`. **The creation pass's account is arithmetically and positionally correct.**

### 7.3 Was the anomaly disclosed rather than silently passed?

**Yes.** V5 §I.2 lines 37–46 disclose it with its own STOP-condition analysis; line 48 states "**Byte counts: 2 / 2 MATCH. Strict digests: 1 / 2**"; line 46 states it "is explicitly NOT reported as a clean `2 / 2 MATCH`"; §22.2 row 8 (line 2900) records it; §22.6 DV-0 (lines 2979–2985) records it again; and §22.6 line 3009 lists it as a disclosed non-material item. The independently located creation report (see §9.4) likewise states the anomaly, the 63-character count, the deletion at position 54, and that it is not reported as a clean 2/2 match.

### 7.4 Decision required by §10

**DV-0 affects process conformance only. It does not undermine the identity of the actual V5 input.** Basis, from measured bytes and available evidence:

- The V4-audit artifact at the exact named path is **43766 bytes — exactly the stated byte count** — and hashes to a 64-character value that differs from the stated literal by exactly **one deleted character** at a fixed position. It is therefore a one-character-mangled copy of the measured digest, not the digest of any different artifact.
- The V5 **target's** identity (270195 bytes, `d33f9907…39d6b3`) was verified against a **well-formed 64-character** expectation supplied in §1.1 of this work order, which matched exactly. No malformation touches the V5 target's own identity.
- No input was missing, unreadable, substituted, reconstructed or repaired by this audit, and none was by the creation pass (V5 §I.2 lines 42–44). No similarly named file was used.

**I do not retroactively claim that the original V5 work order was correct.** It was not: its stated expected digest for the V4-audit input was malformed. That is recorded here as a work-order defect, disclosed by the creation pass rather than concealed.

### 7.5 ADV-1 — recurrence, this round (work-order side; NOT a V5 defect)

**ADV-1 (LOW, advisory).** §1.3 of *this* work order presents a digest literal for the V4-audit input and asserts it is "the corrected 64-character digest". The literal **as delivered to this pass** is again **63 characters**, with the same character (`2`, 1-based position 54) absent — a recurrence of the DV-0 pattern. Effect: **none on the audited artifact and none on input identity** (the V4-audit file's identity is established by exact byte count plus the 64-character measured digest, which is documented in V5 and reproduced here). Recommended action: when the work order is re-issued or archived, replace the §1.3 literal with the measured 64-character value; treat the literal, not the file, as the defective element.

**Cause — stated as INTERPRETATION, not as a byte fact.** I cannot determine from inside this execution whether the work order was authored with a 63-character literal or whether one character was lost in delivery to this pass. Evidence that a delivery/rendering channel can lose exactly one character from a long hex run: (a) in a prior pass in this same environment, a terminal digest produced by `hashlib` was rendered back in the operator-facing message with the identical single-character loss; and (b) the same channel exhibits asterisk-run distortion in both directions (see §10.3). I therefore record both possibilities and take the **measured** value as authoritative. Under a strictly literal reading of §1.3, a 63-character expectation would be a STOP/BLOCKED trigger; because the identity is independently established by exact bytes, I treat it as a disclosed process-conformance defect and proceed — and I flag it here rather than passing it silently.

---

## 8. AUTHORIZATION AND DECISION GATES (§11 of the work order)

### 8.1 D-1 … D-4 remain OPEN

Verified at every layer of V5 that states them: §I.7 item 3 (line 148, V5's own); §4.4 rows (lines 728–731, V2-origin body carried); §20.4 rows (lines 2562–2565, V3's own); §21.4 rows (lines 2760–2763, V4's own); §22.4 rows (lines 2944–2947, V5's own); §12/§15/§19 status tables (lines 2023, 2025–2026, 2149–2152, 2172–2175, 2432–2435); the three footer lines (2851, 2662, 3072); and the terminal line (3082).

- **D-1** (Alembic Branch A vs Branch B) — `OPEN / BLOCKED`, "**No branch selected.**" (line 2944). Part II §11 branches remain "applies only if selected" (lines 1951, 1979).
- **D-2** (target OS / `PLATFORM_PROFILE`) — `OPEN / BLOCKED`, "**No platform selected.**" (line 2945); §10.3 runner pin stays BLOCKED (line 1919).
- **D-3** (mode provenance / runtime-test contract) — `OPEN`, "**No option selected**" (line 2946); §7's O1/O2/O4 stated with five attributes each, O3 disallowed.
- **D-4** (percent-encoded database component policy) — `OPEN`, "**No policy selected**; PT-12 stays OPEN" (line 2947); the stricter `REFUSE` remains labelled a recommendation.

### 8.2 No silent selection; recommendations stay recommendations

An exhaustive sweep for `select|decid|adopt|chosen|chose` over all 3082 content lines returns only: conditionals ("only if the operator selects that branch"), negations ("Nothing in V5 selects a migration branch, a target platform profile, a runtime/test contract, or a percent-encoding policy" — line 2949–2951), descriptions of runtime/engine branching (e.g. `session.py:167` selecting a pool class), and statements about the digest rule's selectivity. **No line selects or implies a selection of any operational option.** §22.4 lines 2949–2951 state that every recommendation is a `DESIGN-RECOMMENDATION`, never an operator decision.

### 8.3 Authorization boundary — measured, not asserted

- **`NOT GRANTED` occurs 51 times.** Every line carrying it is either an authorization gate (V5 lines 13–15, 181–183, 336–338, 473–475, 2649–2651, 2838–2840, 3059–3061 — **21 gate lines, each with exactly 4 asterisks, balanced, by `str.count`**) or non-permissive prose about the defect/format of such statements.
- **`GRANTED` occurs 60 times.** All 60 occurrences were inspected with left context: **every one is preceded by `NOT ` or `NOT-`** (or is the tail of a quoted gate inside a table). **There is no permissive grant anywhere.**
- **`AUTHORIZED` (US spelling, uppercase) occurs exactly 2 times:** line 3050 (the inherited condition "`AUTHORIZED` (US, operative) `= 0`" quoted inside §22.7's grant-token accounting) and line 3082 (the mandated restrictive boundary line, "IMPLEMENTATION NOT AUTHORIZED"). `AUTHORISED` (UK spelling, uppercase) occurs **0** times. §22.7's claim that "the US-spelled uppercase grant token occurs **twice** in this document" is therefore **verified as measured**, and both occurrences are restrictive or meta-referential.
- **`AUTHORIZED (US, operative) = 0`** is preserved in its intended sense: no operative grant exists; the two occurrences above are restrictive.
- **`DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` occurs 59 times** and is never transformed into an implementation-success claim. V5 §I.7 line 145 states "**V5 claims that no guard is implemented or tested.**" §22.7 lines 3044–3045 states "V5 makes **no claim that any guard has been implemented or tested**; finding F-V7's specification-level qualification, carried in Part II at §16.6 G10, remains in force."
- **Self-acceptance language:** the 8 occurrences of `ACCEPTED`, 4 of `PRODUCTION READY` and 4 of `VERIFIED IMPLEMENTATION` were each inspected; **every one is a negation ("contains no `ACCEPTED`…"), a historical citation of an earlier audit's verdict, or a statement that a matrix item is not marked ACCEPTED.** V5 offers no verdict on itself (§I.4 101–103; §I.7 item 4; §22.1 2881–2882).
- **No language authorizes implementation, testing, repository mutation, publication or deployment.** V5 §22.7 (3039–3045), §I.7 item 5 (153) and the terminal italic block (3080, 3082) all state the prohibition affirmatively.

### 8.4 Footer / gate internal consistency

V5 carries four gate-and-footer blocks (V5's own at 13–15, V4's at 181–183, V3's at 336–338, and V2's at 473–475), plus V4's own §21.7 footer at 2838–2840 with its closing italics at 2847–2859, plus V5's own §22.7 at 3059–3061 with its closing italics at 3068–3080. **Every gate line in all seven blocks carries exactly 4 asterisks (balanced); every closing italic line carries an even, self-balanced count** — including line 2849, which the console rendered without its closing asterisk but whose stored bytes carry stars at indices [0, 230]. Consequently §21.7's markup note (2833–2836), §22.7's markup note (3054–3057) and the change-log rows about markup (2896) are **accurate as measured**. This is a source-byte fact, not a rendering judgment (see §10.3).

---

## 9. EVIDENCE CLASSIFICATION (§12 of the work order)

### 9.1 SOURCE-BYTE FACT — measured directly from the exact stored input by this pass

V5's byte count, full-file SHA-256, LF-only endings, single trailing LF, 3082 content lines and non-truncation; the non-embedding of V5's own digest; the series-digest selector's uniqueness at line 2971, the single 64-hex token on line 2972, the length-preserving substitution and the reproduced digest; the locations of the three carried labels (2783, 2588, 2284); V4's byte count/SHA-256 and its own label at 2601 with its re-derived series digest; the V4-audit byte count/SHA-256 (64 chars); all 12 §I.3 upstream identities re-measured from disk; V4's header block lines 1–16 (title, seven metadata lines, three gates with 4 asterisks each); V5's header block lines 1–16; the Part II boundaries (V5 169 and 2859 byte-equal to V4 1 and 2673); the five-hunk alignment and the exact anchor ranges; the 2673 → 2691 arithmetic; the byte-identity of V4's §21.3 eleven-anchor table in Part II; the byte content of the two corrected §I.4/§21.1 paragraphs, the corrected §21.3 additions note and the corrected §21.6 DV-6 bullet; the `C-V3-3` requirement cell's retained `§20.1–§20.6` and resolution `§20.1–§20.7`; the counts `NOT GRANTED` 51 / `GRANTED` 60 (all preceded by NOT/NOT-) / `AUTHORIZED` 2 / `AUTHORISED` 0 / `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` 59 / `IMPLEMENTATION NOT AUTHORIZED` 1; every gate and closing line's asterisk inventory in all seven blocks; the terminal content line 3082; and the absence of `_v5_build.py` / `_v5_amend.py` from the output directory at audit time.

### 9.2 INDEPENDENTLY REPRODUCED — recomputed or compared by this pass against a source other than the claim under test

The series digest (re-implemented from the rule text, not from the reported value); V4's series digest (re-derived from V4's own bytes); the five-hunk alignment (re-run from the frozen V4 file, not read from V5); the line arithmetic (recomputed from hunk lengths); the duplicate-title-related and anchor-identity checks inside V4's own §21.3 table; the 12/12 upstream identity table; the README-level statement that V4's §21.3 table is byte-identical in Part II (via the equal region, not via V5's assertion).

### 9.3 INHERITED CLAIM — carried from an earlier report and **not** re-derived here

- The V4 audit's own findings `F-4A`, `F-4B`, `F-4C` and conditions `C-4-1`, `C-4-2`, `C-4-3` were **read from the V4 audit's bytes** (§9 and §10 of that report) — so the *content* of the findings is source-read, but the audit's underlying reasoning about V1/V2/V3 bytes is inherited, not re-derived.
- V5 §22.1 row 2's basis ("as the V4 audit itself established") is correctly self-labelled as inherited; I verified the anchor identities against V4's §21.3 table (§5), which corroborates it, but I did not re-read V1/V2/V3.
- The `NV-2` / `NV-5` items in Part II remain `AUDIT-CONFIRMED` / `QUALIFIED` (V5 §22.6 DV-3, lines 2994–2995). **V5 does not upgrade them; neither do I.**
- V4's §21.6 DV-7 and DV-8 records carried unchanged in Part II (V5 §22.6 DV-7, lines 3018–3019).
- The carried V2 and V3 series digests (`a96ee5c4…`, `e748e8b8…`) were cross-checked for label placement only; their values were not re-derived from V2/V3 files (which this pass did not read for content).

### 9.4 AUTHOR-SESSION CLAIM — asserted by a producing pass; not independently observable by this audit

V5's own process claims: the pre-write existence check (V5 §22.2 row 3); the "written once and re-generated once" claim (§22.6 DV-11); the two pre-write builder iterations (§22.6 DV-6 items (ii)/(iii)); the tooling-placement claims (§22.6 DV-5); and the analogous V4-session claims carried from V4. V5 labels each of these correctly (`AUTHOR-SESSION CLAIM`; the §I.5 legend adds the tag explicitly, line 117).

**The V5 creation report (work order §1.4).** The completion report for `WO-PRE-3-V5-DOCUMENTARY-CORRECTION` is **not present at any known filesystem path** in the audited output directory (one-level listing: no such file). It exists as a **chat record** in the local Hermes session store — session `api-bcbc08e9f0501b30`, message id 35120 — which this pass read. **I did not hash any report file, and I do not claim to have done so.** Its reproducible claims were checked against measurement and **all of them reproduce**: the series digest and its selector line number; "AUTHORIZED count: 2"; the boundary line present and final; the gate-line list and 4-asterisk counts; the five-hunk alignment and the +18 net; the V4/V4-audit identities unchanged; the removal of the builder script from the output directory. Its non-reproducible claims (its own iteration history, the pre-write existence check) remain **author-session claims**.

### 9.5 INTERPRETATION — reasoned assessment, not a byte fact

That the §1.3 literal defect is most likely a delivery-channel effect (§7.5); that the corrected §I.4/§21.1 wording "narrows a preservation claim without weakening a control"; that the `C-V3-3` annotation is "outside the quoted requirement" although it sits within the same table cell (the quoted requirement string is byte-unchanged, which is the operational test).

---

## 10. NEW FINDINGS, NON-FINDINGS, DEVIATIONS AND LIMITATIONS

### 10.1 New findings

**None against V5.** No material claim of V5 within the authorized evidence scope failed to reproduce; no V5 control is unsafe; no V5 statement silently selects an operator decision; no undeclared change to V4 exists.

**ADV-1 (LOW — advisory, work-order side).** As detailed in §7.5: the §1.3 digest literal for the V4-audit input as delivered to this pass is again 63 hex characters (DV-0 recurrence). It is recorded as an advisory on the work order, **not** as a condition on V5, and it does not affect the identity of any input.

### 10.2 Non-findings recorded for completeness (no correction proposed)

1. **`C-V3-3` annotation placement.** V5 §22.3 anchor 5 (line 2922) says the annotation is added "**outside** the quoted requirement". The annotation sits inside the same table cell, appended after the quoted requirement text; the quoted requirement body — including the `§20.1–§20.6` form — is **byte-unchanged**, and the resolution column still reads `§20.1–§20.7`. The operational test (is the quoted requirement altered?) is satisfied; only the word "outside" is loose, and the row itself is marked "optional advisory". **No correction required.**
2. **§22.3 anchor-2 wording "anchors 2, 3, 5, 7 and 8 named".** This is the union of the sets the corrected Part II text states (2, 3, 7, 8 in the `C-V2-1` narrative; 5 in the §15 note). Set-correct; only the ordering differs from the Part II prose. **No correction required.**
3. **Granularity of the header inventories.** Neither the V4-facing correction (2748–2754) nor V5's own additions note (2933–2938) names the header's connecting heading line 11 or blank lines 2/10/12/16. The F-4A requirement was to name lines 1–16, the title, the cover metadata and the gate lines 13–15 — all present — and the same granularity is used consistently. **No correction required.**
4. **Both `§21.7` and `§22.7` say "the gates stated at the head of this document".** Each is correct within its own pass; V5 §22.6 DV-8 (3020–3022) discloses exactly this ("Both footers are internally consistent, each within its own pass"), and the Part II banner fixes the referent for the carried block. **No correction required.**
5. **V5's own §22.6 DV-6 and V4's corrected §21.6 DV-6 share a heading.** Each is a deviation register of a different pass, in a different part of the document; the Part II banner disambiguates "this pass". **No correction required.**
6. **The §22.1 status vocabulary.** The preamble names three permitted statuses; row 4 uses `CORRECTED — QUALIFIED` with an "(optional)" qualifier. Consistent with the preamble's three terms. **No correction required.**

### 10.3 Deviations, limitations and failed operations — disclosed in full

- **Filesystem access was bounded.** Access was limited to one-level listings of `/opt/data/output` and reads/hashes of explicitly named files, plus typical test of the designated output path. **No recursive listing, no `os.walk`, no broad glob, no traversal of the repository root** was performed.
- **No repository access of any kind.** No Git command was run (not even a status), no branch or worktree state was inspected, no remote was contacted, no branch was switched, and no Git mutation command of any kind was issued. **The protected path `?? 500` was not observed, opened, read, hashed, stat-ed, traversed, copied, moved or staged — it was not even seen, because no repository status was taken.** This is deliberate and is not a skipped step.
- **No application or third-party source was read.** No test, import, engine construction, database connection, migration or application startup was attempted or executed. No code or guard was implemented.
- **Reading completeness.** V5 was read in full for its own content — Part I (lines 1–154) and Part III (lines 2861–3082) were read line by line, and the whole file was subjected to byte-level sweeps (counts, hex dumps, selector scans, per-line asterisk inventories). **The Part II body (V5 lines 169–2859 — V4's carried content) was not read line by line**; its fidelity to V4 was established mechanically by the deterministic alignment (§3.3) and its touched regions were read in full. V4 was read at: lines 1–16, 2509–2518, 2548–2574, 2626–2630 (via the diff), 2661–2673. The V4 audit was read at: its heading map, §9 (lines 361–369), §10 (373–381), §11–§12 (385–402) and the section list. **V1, V2 and V3 were hashed but NOT read.** All upstream artifacts other than V4 and the V4 audit were hashed only, for identity.
- **A source read only as a session record.** The V5 creation report was read from the local session store (§9.4), not from a file. No digest of it exists or is claimed.
- **Rendering limitation re-observed, and handled.** The console again distorted asterisk runs in both directions, e.g. it displayed `**Implementation authorization:*** NOT GRANTED` (visually 5 asterisks before `NOT`) where the stored bytes carry exactly 4 (`**` + `:**`), and it displayed the self-balanced italic lines `*Implementation authorization: NOT ***` and `*This document claims no acceptance … (§21.5).` where the stored bytes carry exactly 2 stars at the line's first and last position. **Every asterisk-bearing, backtick-bearing or long-hex conclusion in this report rests on hexadecimal dumps, `str.count`, exact list equality or `difflib` opcodes — never on displayed text.** This limitation is the same class V5 discloses at its §I.6 and §22.6 DV-4.
- **No hash was taken from rendered output.** All digests in this report were computed by `hashlib.sha256` over bytes read from disk in this pass.
- **Sandbox artifact.** The code-execution sandbox materialised an ephemeral script under `/tmp`; it was not written into the repository or the output directory, and no artifact was affected.
- **Output path.** Confirmed absent before writing; the report was written to the exact designated path only. No other file was created, modified, renamed, moved or deleted by this pass.
- **No defect silently repaired.** No text of V5, V4 or the V4 audit was altered; the F-4A/F-4B/F-4C corrections were **verified only**, never rewritten, and ADV-1 was recorded rather than fixed.
- **Failed operations in this audit: none.** No command failed, no input identity mismatched, no source was inaccessible, and no protected-path boundary was approached.

### 10.4 Explicit list of historical claims NOT re-derived by this pass

1. The V4 audit's reasoning over V1/V2/V3 bytes (its §2–§6) — read as a document, not re-executed against V1/V2/V3.
2. V1's, V2's and V3's contents in general (hashed only; never read) — hence every source citation inside Part II remains the statement of the gate that made it (V4, V3 or V2), exactly as V5 §I.6 states (lines 128–131).
3. `NV-2` and `NV-5` — remain `AUDIT-CONFIRMED` / `QUALIFIED`, not upgraded (V5 §22.6 DV-3).
4. V4's §21.6 DV-7 and DV-8 — carried unchanged, not re-derived.
5. The V2 and V3 series digests carried in V5 — label placement verified; values not re-derived from V2/V3 files.
6. All author-session process claims of the V4 and V5 gates (§9.4), including the V5 output's own single regeneration and the two pre-write builder iterations.
7. The V4 audit's verdict `ACCEPTED WITH CONDITIONS` — carried as history, not re-adjudicated.

---

## 11. NON-MUTATION STATEMENT (§13.11 of the work order)

This audit **did not modify** V5, V4, the V4 audit, or any other existing artifact. It created exactly one new file — this report — at the designated new path, which was verified absent beforehand. It ran no Git command, entered no repository, accessed no application source, executed no test, started no application, constructed no engine, opened no connection, ran no migration, published nothing, deployed nothing, and authorized nothing. No subsequent work order was started; no PRE-5 or later work was begun.

Measured immediately after this report was written (read back from disk):

| Artifact | Bytes | SHA-256 | Status |
|---|---|---|---|
| `PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V5.md` | 270195 | `d33f990715f6fb5563217f1c1664dc3be2bc1ff55ade5a04d1483bddeb39d6b3` | **unchanged** |
| `PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V4.md` | 230449 | `694ea3b62c6a1fb96da042f5d30fb0174db2ec47dd78f9e9cf89584677ec27fb` | **unchanged** |
| `PRE-3-CORRECTED-V4-INDEPENDENT-RE-AUDIT.md` | 43766 | `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0` | **unchanged** |

This report contains **no digest of itself**; its stored-file byte count and SHA-256 are reported externally, in the terminal response to this work order. Its own series-convention digest is likewise not embedded.

---

## 12. CONDITIONS

**None on V5.** The three conditions of the V4 audit — `C-4-1`, `C-4-2`, `C-4-3` — are each **resolved, verified from the stored bytes**, and closed at the level of V5's documentary content. No bounded correction remains outstanding against the audited artifact.

**One advisory on the work order — ADV-1** (§7.5): replace the §1.3 digest literal with the measured 64-character value when this work order is archived or re-issued. Non-blocking; no effect on V5 or on input identity.

---

`PRE3_V5_INDEPENDENT_RE_AUDIT_VERDICT = ACCEPTED`

IMPLEMENTATION NOT AUTHORIZED. D-1 THROUGH D-4 REMAIN OPEN.
