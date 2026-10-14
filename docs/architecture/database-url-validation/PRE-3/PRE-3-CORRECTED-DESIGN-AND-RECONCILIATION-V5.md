# PRE-3-CORRECTED-V5 — DESIGN CORRECTION AND RECONCILIATION (FIFTH BOUNDED CORRECTION PASS)

**Document type:** Corrected design report (documentation only — NO implementation)
**Work order:** WO-PRE-3-V5-DOCUMENTARY-CORRECTION — bounded documentation-only correction of PRE-3 V4
**Mode:** STRICT DOCUMENTATION-ONLY / EXTERNAL REPORT ONLY. The repository was **not** entered, read, listed, stat-ed or modified by this pass. **No Git command of any kind was run by this pass.**
**Repository (unchanged; not accessed for source by this pass):** `yarem44uk/TACTICAL_CORE`
**Branch (carried from V4, which carried it from V3; not re-observed):** `main`; the baseline `1f20e9a867ce7d286e6e72a71ddefeec8f7f9264` is **carried as V3's and V4's statement**, not re-measured here (§I.6, §22.6 DV-2). The remote was **never contacted**.
**Supersedes (as design guidance):** PRE-3 V4, identified in §I.2. V4 is **not** modified, renamed, moved or deleted by this pass. It is preserved **byte-for-byte** at the identity recorded in §I.2 and remains the exact artifact its independent re-audit addressed.
**New artifact:** yes — one **new, additional** file. V1, V2, V3, V4, the V1/V2/V3/V4 audits, PRE-1, PRE-2, the current PRE-3 and the previous audit are all preserved unmodified (§I.2, §I.3).

**Authorization gates — unchanged by this pass:**

**Implementation authorization:** NOT GRANTED
**Git commit / push authorization:** NOT GRANTED
**Production deployment authorization:** NOT GRANTED

## Part I — V5 cover: identity, inputs, scope and preservation

### I.1 Purpose of this pass (bounded)

Resolve the **three** LOW-severity documentary findings (`F-4A`, `F-4B`, `F-4C`) that the independent re-audit of
V4 raised against V4's own change documentation, and otherwise **preserve V4's corrected content**. V5 is
therefore "V4 plus bounded documentary corrections", not a rewrite. **No application code, test, CI job,
configuration, migration or guard is implemented, and nothing is published or deployed.** This pass resolves no
operator decision and closes none of `D-1`…`D-4`.

Every change made by this pass is labelled **`AUDIT-DRIVEN CORRECTION (V5)`**, and the superseded V4 statement is
named so the audit trail is complete. **No new design decision is taken and no operator decision is taken.**

### I.2 Input identity verification — measured from disk before any edit

| Input | Path | Expected bytes | Measured bytes | Expected SHA-256 | Measured | Result |
|---|---|---|---|---|---|---|
| **V4** (corrected report) | `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V4.md` | `230449` | **230449** | `694ea3b62c6a1fb96da042f5d30fb0174db2ec47dd78f9e9cf89584677ec27fb` | identical | **MATCH** |
| **V4 audit** (independent re-audit) | `/opt/data/output/PRE-3-CORRECTED-V4-INDEPENDENT-RE-AUDIT.md` | `43766` | **43766** | `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbea1a2c675f0` *(63 hex chars as received — see DV-0)* | `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0` | **BYTES MATCH; EXPECTED DIGEST MALFORMED — DV-0** |

> **DV-0 — input-identity anomaly (flagged, disclosed; NOT silently passed).** The work order's stated expected
> SHA-256 for the V4 audit is **63 hexadecimal characters**, one short of any valid SHA-256. The artifact at the
> exact named path is **43766 bytes — exactly the stated byte count** — and hashes to the 64-character value
> `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0`. The stated value equals that measured
> value with **exactly one character deleted** (position 54, hex `2`) — i.e. it is a one-character-mangled copy of
> the measured digest, not the digest of any different artifact. **The input is therefore identified as the exact
> named artifact (path + exact byte count + all-but-one digest character) and is used; no other artifact was
> substituted and none was reconstructed.** Recorded as `DV-0` (§22.6). **Under a purely literal reading of the
> work order's §1.3 this anomaly would be a `STOP` / `BLOCKED` condition; it is disclosed here so the independent
> auditor can adjudicate it, and it is explicitly NOT reported as a clean `2 / 2 MATCH`.**

**Byte counts: 2 / 2 MATCH. Strict digests: 1 / 2** — the V4 digest matches exactly; the V4-audit *expected*
value as received is malformed (63 hex characters, `DV-0`). Neither input was missing, unreadable, substituted,
reconstructed or repaired. **Both were read in full** before any correction (V4: **2673** content lines plus a
final empty element; the V4 audit: **402** content lines). Had either input been missing or its identity
unconfirmable, this pass would have reported `BLOCKED` and created nothing.
`[SOURCE-BYTE FACT: os.path.getsize + full-file SHA-256, measured outside the repository]`

The V5 output path was checked **before** the write and held **no pre-existing file**; no file was overwritten,
renamed, moved or deleted. **V4 and the V4 audit were read back and re-hashed AFTER the V5 write and are
unchanged** (§22.5), as are all upstream artifacts in §I.3.

### I.3 Upstream preservation re-check (re-hashed from disk; not read for source)

| Input | Bytes (measured) | SHA-256 (measured) | Result |
|---|---|---|---|
| **V4** (predecessor report) | 230449 | `694ea3b62c6a1fb96da042f5d30fb0174db2ec47dd78f9e9cf89584677ec27fb` | **MATCH** to the identity fixed by the earlier passes |
| **V4 audit** | 43766 | `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0` | **MATCH** to the identity fixed by the earlier passes |
| V3 | 195740 | `76ec61a41901de18fc8c2d6005b973d8836e31973134746a047afeefc8f862ef` | **MATCH** to the identity fixed by the earlier passes |
| V3 audit | 43640 | `1bb9ced90fe6897c91b1476cb9a903b2636c9177f2f7d946fdc1430897f0fe28` | **MATCH** to the identity fixed by the earlier passes |
| V2 | 156249 | `3721a17e03b5861ffea646a7857a72f8e7a6daf77c14c1aad8c8644dc781e611` | **MATCH** to the identity fixed by the earlier passes |
| V2 audit | 51456 | `15ef2d6398a1f17edb83d097a62c7e0c4942f29e35fe9dbd3ddf6b178177bd41` | **MATCH** to the identity fixed by the earlier passes |
| V1 | 97686 | `a9418f4f8a3dccaec0dee3cc00b70f8f74c4c3fae92c290eb5c2ca6bc458b328` | **MATCH** to the identity fixed by the earlier passes |
| V1 audit | 56724 | `6d64ae5be6f9cee5856c1a1c84feb97672f29ee3515ee77aeba70fe14f9adc72` | **MATCH** to the identity fixed by the earlier passes |
| PRE-1 | 41034 | `cc7e5647e36192426a9da08d9364b53e1c13239f12d95d1318b63601ae5ffcd4` | **MATCH** to the identity fixed by the earlier passes |
| PRE-2 | 66793 | `b2d955db05b6c3644ce0f640865f5ccf7e04a54b99375a74077a36a6e812471c` | **MATCH** to the identity fixed by the earlier passes |
| PRE-3 (current) | 68327 | `2d1bd878117fa48cf83824622387829b55d63209bfc3cfddf74fe01bd00cfb46` | **MATCH** to the identity fixed by the earlier passes |
| previous audit | 77918 | `1d4a2503916b452535ac5b722a68ed23c63afa78113b0c3a74e1f09b55d2a4a2` | **MATCH** to the identity fixed by the earlier passes |

**12 / 12 reproduce.** Every one was re-hashed from disk after the V5 write and is unchanged.
This pass altered no earlier artifact.
`[SOURCE-BYTE FACT: fresh full-file SHA-256 per file]`

### I.4 Relationship to V4 (what is preserved, what is corrected)

**Preserved.** V4 is carried forward in Part II **in full** — its Part I cover, its Part II (V3's carried body)
and its Part III (§21.1–§21.7). The **only** V4 regions this pass rewrites are the **five** anchors listed in
§22.3 (four required corrections plus one optional quotation annotation), each a direct response to a named
finding or advisory of the V4 re-audit. **Every technical conclusion, evidence boundary, source citation, table,
test specification, open-decision record and authorization restriction of V4 that is not listed in §22.3 is
carried forward byte-identically.**

**Corrected.** §22.1 maps each finding to the V5 section that resolves it, the basis on which it was verified in
this pass, and its status. The three findings are `F-4A` (the §21.3 additions inventory did not name V4's own
header block), `F-4B` (the "carried in Part II unchanged" wording overstated the byte-preservation of prose) and
`F-4C` (the §21.6 DV-6 heading contradicted its own disclosed `NameError`).

**Preserved without re-grading (explicitly).** As V4 stated of V3, the V4 dispositions of `C-V2-1`, `C-V2-2`,
`C-V2-3` and of advisories `NV-2`, `NV-4`, `NV-5`, `NV-6`, `NV-7` are carried in Part II with the **statuses V4
gave them — carried forward, not byte-identical prose**: the explanatory text around those statuses is subject
**only to the explicitly declared** V4 anchors of §21.3 (carried) **and** to V5's own declared anchors of §22.3.
V5 makes no new claim about them and does not re-grade them. The `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED`
status of every design item is likewise unchanged.

**No refutation of inherited findings.** V5 reclassifies, strengthens and withdraws **no** inherited audit finding
or verdict. The V4 re-audit's verdict (`ACCEPTED WITH CONDITIONS`) and all earlier verdicts are carried as
**historical**, at the grade their own passes gave them. **V5 offers no verdict on itself** (§22.7).

### I.5 Claim-tag legend (carried from V4; one addition)

| Tag | Meaning |
|---|---|
| **SOURCE-CONFIRMED** | Read directly by the gate named in the passage, from the committed tree at the branch's baseline or from third-party library source, with `path:line` given. In Part II this tag therefore means "confirmed **by V3**" (and, for V2-origin citations, "confirmed **by V2**"). |
| **AUDIT-CONFIRMED** | Asserted by an independent audit and carried because re-derivation was outside the reading scope of the gate carrying it. |
| **DESIGN-RECOMMENDATION** | Proposed design. *Not implemented.* |
| **OPERATOR-DECISION** | Cannot be derived from the repository. Requires the operator. |
| **UNVERIFIED** | Runtime, deployment or process fact not established by a read-only gate. |
| **AUDIT-DRIVEN CORRECTION** | A statement changed in direct response to an audit finding. The superseded statement is named. In Part II the marker `AUDIT-DRIVEN CORRECTION (V4)` means the change was made by **V4**; the marker `AUDIT-DRIVEN CORRECTION (V5)` means the change was made by **this** pass. |
| **SOURCE-BYTE FACT** | A conclusion derived from a hexadecimal dump or an exact byte/list comparison of a file on disk — never from visually rendered text (§I.6). |
| **INTERPRETATION** | A reading of evidence (typography, markdown rendering, reachability) that is **not** itself byte-obtainable. **A trailing asterisk alone does not establish an unclosed span** (carried: §5.25, §20.2 item 7a). |
| **AUTHOR-SESSION CLAIM** *(added by V5)* | A process fact about the pass that produced a predecessor artifact, asserted by that pass and **not independently reproducible** by a later reader (e.g. a pre-write existence check, or a corrected script error). |

### I.6 Reading completeness, method, and the rendering-artifact warning

- **V4:** read in **full** (2673 content lines plus a final empty element) before any correction.
- **V4 audit:** read in **full** (402 content lines), including its bottom line, §2 (the V3 carry-forward), §3–§6
  (the C-V3 and F-V findings), §7 (controls and open decisions), §8 (deviations), §9 (the new findings `F-4A`,
  `F-4B`, `F-4C`) and §10 (conditions).
- **V1, V2 and V3 were NOT read by this pass.** Unlike V4, this pass's corrections require **no** bytes of V1, V2
  or V3: the three findings are internal-consistency matters of V4's own change documentation. Only V4's and the
  V4 audit's bytes were read, and only in the region of the corrections. `[SOURCE-BYTE FACT]`
- **Repository and third-party source were NOT read by this pass.** This work order is documentation-only and
  authorises no repository access for source. Every repository and third-party citation in Part II is therefore
  carried as V4's (or V3's, or V2's) statement and is **not** re-asserted as `SOURCE-CONFIRMED` by V5. **No new
  source claim is made anywhere in this document.**
- **Rendering-artifact warning (carried; material to every quotation in this document).** This gate's own tool
  output **distorts asterisk runs and some adjacent characters** in *displayed* text: a stored bold or italic run,
  or a plain colon or closing backtick, can be shown with a spurious additional asterisk. V3 (its DV-4), the V3
  audit (its DV-D), V4 (§21.6 DV-4) and the V4 audit (its DV-D) each disclosed this class of artifact, and it is
  **observed again in this pass** (§22.6 DV-4). **Consequently every asterisk-bearing or quotation-critical
  conclusion in this document rests on a hexadecimal dump, an exact `str.count`, or a list comparison of the file
  bytes — never on rendered text.** The artifact is a real property of the tooling and is kept strictly separate
  from file content.

### I.7 Scope limits of this pass (what V5 does not do)

1. **No implementation.** No code, test, CI step, workflow, configuration, migration, guard, redactor or logging
   change is written, or claimed to exist. The `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` status of every
   design item in Part II is unchanged. **V5 claims that no guard is implemented or tested.**
2. **No re-derivation of Part II's source evidence** (see §I.6, §22.6 DV-2/DV-3). V5 carries V4's citations and
   does not upgrade them.
3. **No operator decision.** `D-1`, `D-2`, `D-3` and `D-4` remain **OPEN** (§22.4). Nothing in V5 selects a
   migration branch, a target platform profile, a runtime/test contract, or a percent-encoding policy.
4. **No acceptance of itself.** V5 contains no `ACCEPTED`, `VERIFIED IMPLEMENTATION` or `PRODUCTION READY`
   verdict. It is offered for independent re-audit pinned to its stored-file SHA-256, which is reported in the
   terminal response and **not** embedded here (§22.5).
5. **No repository mutation, no Git mutation, no remote contact, no publication, no deployment** (§22.6, §22.7).

## Part II — Carried-forward V4 body

> **Disambiguation banner (V5) — governs all of Part II.** Part II is **V4 content preserved as evidence**, with
> the exceptions listed in §22.3 marked **`AUDIT-DRIVEN CORRECTION (V5)`**. Inside Part II, *"this gate"*,
> *"this pass"*, *"this report"*, *"this file"*, *"V1"*, *"V2"*, *"V3"* and *"V4"* refer to the **V4
> authoring gate and its documents** — not to the V5 gate; V4's own banner below additionally defines how V4's
> Part II refers to V3. Part II carries V4's own Part I cover, V4's Part II (V3's carried body) and V4's Part III
> (§21.1–§21.7) unchanged except at the anchors declared in §22.3; V5's own cover is Part I above, and V5's own
> corrections are Part III below (§22.1–§22.7). The `# PRE-3-CORRECTED-V4 …` heading that follows is **V4's own
> title, preserved verbatim**. Part II therefore ends with **V4's own footer** (§21.7 of V4); V5's own gates are at
> the head of this document and in §22.7 (§22.6, DV-8). V4's terminal digest label reads `- **V4 SHA-256 …`,
> V3's reads `- **V3 SHA-256 …` and the carried V2 label reads `- **SHA-256 …`; none of those three is selectable
> by V5's own digest rule (§22.5), which keys on the literal `- **V5 SHA-256`.

# PRE-3-CORRECTED-V4 — DESIGN CORRECTION AND RECONCILIATION (FOURTH BOUNDED CORRECTION PASS)

**Document type:** Corrected design report (documentation only — NO implementation)
**Work order:** WO-PRE-3-V4-DESIGN-CORRECTION — bounded documentation-only correction of PRE-3 V3
**Mode:** STRICT DOCUMENTATION-ONLY / EXTERNAL REPORT ONLY. The repository was **not** entered, read, listed, stat-ed or modified by this pass.
**Repository (unchanged; not accessed for source by this pass):** `yarem44uk/TACTICAL_CORE`
**Branch (carried from V3; not re-observed):** `main`; V3's recorded baseline `1f20e9a867ce7d286e6e72a71ddefeec8f7f9264` is **carried as V3's statement**, not re-measured here (§I.6, §21.6 DV-2). The remote was **never contacted**.
**Supersedes (as design guidance):** PRE-3 V3, identified in §I.2. V3 is **not** modified, renamed, moved or deleted by this pass. It is preserved **byte-for-byte** at the identity recorded in §I.2 and remains the exact artifact its independent re-audit addressed.
**New artifact:** yes — one **new, additional** file. V1, V2, V3, the V1/V2/V3 audits, PRE-1, PRE-2, the current PRE-3 and the previous audit are all preserved unmodified (§I.2, §I.3).

**Authorization gates — unchanged by this pass:**

**Implementation authorization:** NOT GRANTED
**Git commit / push authorization:** NOT GRANTED
**Production deployment authorization:** NOT GRANTED

## Part I — V4 cover: identity, inputs, scope and preservation

### I.1 Purpose of this pass (bounded)

Correct the **three** mandatory defects (`C-V3-1`, `C-V3-2`, `C-V3-3`) and address the **four** advisories
(`F-V5`, `F-V6`, `F-V7`, `F-V8`) that the independent re-audit of V3 identified, and otherwise **preserve
V3's corrected content**. V4 is therefore "V3 plus bounded corrections", not a rewrite. **No application
code, test, CI job, configuration, migration or guard is implemented, and nothing is published or deployed.**

Every change made by this pass is labelled **`AUDIT-DRIVEN CORRECTION (V4)`**, and the superseded V3 statement
is named so the audit trail is complete. **No new design decision is taken and no operator decision is taken.**

### I.2 Input identity verification — measured from disk before any edit

| Input | Path | Expected bytes | Measured bytes | Expected SHA-256 | Measured | Result |
|---|---|---|---|---|---|---|
| **V3** (corrected report) | `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V3.md` | `195740` | **195740** | `76ec61a41901de18fc8c2d6005b973d8836e31973134746a047afeefc8f862ef` | identical | **MATCH** |
| **V3 audit** (independent re-audit) | `/opt/data/output/PRE-3-CORRECTED-V3-INDEPENDENT-RE-AUDIT.md` | `43640` | **43640** | `1bb9ced90fe6897c91b1476cb9a903b2636c9177f2f7d946fdc1430897f0fe28` | identical | **MATCH** |

**2 / 2 MATCH.** Neither input was missing, mismatched, substituted, reconstructed or repaired. **Both were
read in full** before any correction (V3: 2333 content lines plus a final empty element; the V3 audit: 585
content lines). Had either identity failed, this pass would have reported `BLOCKED` and created nothing.
`[SOURCE-BYTE FACT: os.path.getsize + full-file SHA-256, measured outside the repository]`

**V3 was read back and re-hashed AFTER the V4 write and is unchanged** (§21.5), as are all eight upstream
artifacts in §I.3.

### I.3 Upstream preservation re-check (re-hashed from disk; not read for source)

| Input | Bytes (measured) | SHA-256 (measured) | Result |
|---|---|---|---|
| V2 | 156249 | `3721a17e03b5861ffea646a7857a72f8e7a6daf77c14c1aad8c8644dc781e611` | **MATCH** to the earlier passes' records |
| V2 audit | 51456 | `15ef2d6398a1f17edb83d097a62c7e0c4942f29e35fe9dbd3ddf6b178177bd41` | **MATCH** to the earlier passes' records |
| V1 | 97686 | `a9418f4f8a3dccaec0dee3cc00b70f8f74c4c3fae92c290eb5c2ca6bc458b328` | **MATCH** to the earlier passes' records |
| V1 audit | 56724 | `6d64ae5be6f9cee5856c1a1c84feb97672f29ee3515ee77aeba70fe14f9adc72` | **MATCH** to the earlier passes' records |
| PRE-1 | 41034 | `cc7e5647e36192426a9da08d9364b53e1c13239f12d95d1318b63601ae5ffcd4` | **MATCH** to the earlier passes' records |
| PRE-2 | 66793 | `b2d955db05b6c3644ce0f640865f5ccf7e04a54b99375a74077a36a6e812471c` | **MATCH** to the earlier passes' records |
| PRE-3 (current) | 68327 | `2d1bd878117fa48cf83824622387829b55d63209bfc3cfddf74fe01bd00cfb46` | **MATCH** to the earlier passes' records |
| previous audit | 77918 | `1d4a2503916b452535ac5b722a68ed23c63afa78113b0c3a74e1f09b55d2a4a2` | **MATCH** to the earlier passes' records |

**8 / 8 reproduce the identities fixed by the earlier passes.** Every one was re-hashed from disk after the V4
write and is unchanged. This pass altered no earlier artifact.
`[SOURCE-BYTE FACT: fresh full-file SHA-256 per file]`

### I.4 Relationship to V3 (what is preserved, what is corrected)

**Preserved.** V3 is carried forward in Part II **in full** — its Part I cover, its Part II (V2's body) and its
Part III (§20.1–§20.7). The **only** V3 regions this pass rewrites are the **eleven** anchors listed in §21.3,
each a direct response to a named finding of the V3 re-audit. **Every technical conclusion, evidence boundary,
source citation, table, test specification, open-decision record and authorization restriction of V3 that is
not listed in §21.3 is carried forward byte-identically.**

**Corrected.** §21.1 maps each mandatory correction and advisory to the V4 section that resolves it, the basis
on which it was verified in this pass, and its status. The three mandatory corrections are `C-V3-1` (the
"unterminated emphasis span" reading tagged as a byte fact), `C-V3-2` (§20.2 item 8's misattribution of the
three-asterisk form) and `C-V3-3` (the undeclared duplicated title and the incomplete additions note).

**Preserved without re-grading — statuses carried forward, prose not byte-identical (explicitly).** The V3
dispositions of `C-V2-1`, `C-V2-2`, `C-V2-3` and of advisories `NV-2`, `NV-4`, `NV-5`, `NV-6`, `NV-7` are carried
in Part II with the **statuses V3 gave them, unchanged**; **the explanatory prose is not carried byte-identically**.
Five of the eleven declared anchors of §21.3 — anchors 2, 3, 7 and 8 (inside the `C-V2-1` narrative at §5.25 and
§20.2) and anchor 5 (the §15 provenance note inserted under `C-V2-2` / `NV-7`) — edit exactly that surrounding
narrative. The prior dispositions and statuses are therefore **carried forward**, and the explanatory text is
subject **only to the explicitly declared V4 anchors** of §21.3. V4 makes no new claim about them and does not
re-grade them. The `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` status of every design item is likewise
unchanged.  `[AUDIT-DRIVEN CORRECTION (V5) — F-4B]`

**Structural corrections of this pass (disclosed, §21.3).** V4 **deletes** the duplicated V2 title line that
V3 carried at its line 137 (byte-identical to V3 line 138 and to V2 line 1), and corrects §20.3's additions
note so that it declares the `## Part II` heading and Part III §20.1–§20.7.

**Disambiguation that governs all of Part II.** Inside Part II, the self-referential expressions *"this gate"*,
*"this pass"*, *"this report"*, *"this file"*, *"V1"*, *"V2"* and *"V3"* refer to **V3 and its authoring
gate** — not to the V4 gate. Part II is quoted material preserved as evidence about V3. Where a V4 correction
touches a Part II passage, that passage carries an explicit **`AUDIT-DRIVEN CORRECTION (V4)`** marker.

### I.5 Claim-tag legend

| Tag | Meaning |
|---|---|
| **SOURCE-CONFIRMED** | Read directly by the gate named in the passage, from the committed tree at the branch's baseline or from third-party library source, with `path:line` given. In Part II this tag therefore means "confirmed **by V3**" (and, for V2-origin citations, "confirmed **by V2**"). |
| **AUDIT-CONFIRMED** | Asserted by an independent audit and carried because re-derivation was outside the reading scope of the gate carrying it. |
| **DESIGN-RECOMMENDATION** | Proposed design. *Not implemented.* |
| **OPERATOR-DECISION** | Cannot be derived from the repository. Requires the operator. |
| **UNVERIFIED** | Runtime, deployment or process fact not established by a read-only gate. |
| **AUDIT-DRIVEN CORRECTION** | A statement changed in direct response to an audit finding. The superseded statement is named. |
| **SOURCE-BYTE FACT** | A conclusion derived from a hexadecimal dump or an exact byte/list comparison of a file on disk — never from visually rendered text (§I.6). |
| **INTERPRETATION** | A reading of evidence (typography, markdown rendering, reachability) that is **not** itself byte-obtainable. **A trailing asterisk alone does not establish an unclosed span** (§5.25, §20.2 item 7a). |

### I.6 Reading completeness, method, and the rendering-artifact warning

- **V3:** read in **full** (2333 content lines plus a final empty element) before any correction.
- **V3 audit:** read in **full** (585 content lines), including its §3.3 anchor table, §4.4 (F-V1), §4.5,
  §6 (F-V7), §7 (the NV advisories), §9 (DV-1…DV-10 review) and §10 (F-V1…F-V8).
- **V1 and V2 (partial, byte-level, disclosed as DV-1):** the corrections required by C-V3-1, C-V3-2 and F-V5
  cannot be made without the actual bytes, so this pass read **only** the named V1 and V2 line ranges
  (V1 lines 13–15 and 1273–1278; V2 lines 15–17, 670, 674, 1283–1291, 1706–1708) and the file headers needed to
  number them, plus a full-file SHA-256 of each to prove non-modification. No other content of V1 or V2 was
  read. `[SOURCE-BYTE FACT]`
- **Repository and third-party source were NOT read by this pass.** This work order is documentation-only and
  authorises no repository access for source. Every repository and third-party citation in Part II is
  therefore carried as V3's (and, for V2-origin material, V2's) statement and is **not** re-asserted as
  `SOURCE-CONFIRMED` by V4. **No new source claim is made anywhere in this document.**
- **Rendering-artifact warning (material to C-V3-1, C-V3-2 and to every quotation in Part III).** This gate's
  own tool output **distorts asterisk runs and some adjacent words** — for example a stored
  `` `authorization:` `` can be *displayed* as `` `authorization:*** ``. V3 disclosed the same class of artifact
  (its DV-4), the V3 audit disclosed it (its DV-D), and it is **observed again in this pass** (§21.2 row 12).
  **Consequently every asterisk-bearing or quotation-critical conclusion in this report rests on a hexadecimal
  dump, an exact `str.count`, or a list comparison of the file bytes — never on rendered text**
  (§5.25, §20.2). **The rendering artifact is a real property of the tooling and is kept strictly separate
  from file content** — in particular it is **not** the explanation of the three-asterisk run that actually
  exists in V2's stored bytes (§20.2 item 8).

### I.7 Scope limits of this pass (what V4 does not do)

1. **No implementation.** No code, test, CI step, workflow, configuration, migration, guard, redactor or
   logging change is written, or claimed to exist. The `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` status
   of every design item in Part II is unchanged.
2. **No re-derivation of Part II's source evidence** (see §I.6, §21.6 DV-2/DV-3). V4 carries V3's citations
   and does not upgrade them.
3. **No operator decision.** `D-1`, `D-2`, `D-3` and `D-4` remain **OPEN** (§21.4). Nothing in V4 selects a
   migration branch, a target platform profile, a runtime/test contract, or a percent-encoding policy.
4. **No acceptance of itself.** V4 contains no `ACCEPTED`, `VERIFIED IMPLEMENTATION` or `PRODUCTION READY`
   verdict. It is offered for independent re-audit pinned to its stored-file SHA-256, which is reported in the
   terminal response and **not** embedded here (§21.5).
5. **No repository mutation, no Git mutation, no remote contact, no publication, no deployment** (§21.6, §21.7).
## Part II — Carried-forward V3 body

> **Disambiguation banner — governs all of Part II.** Part II is **V3 content preserved as evidence**, with
> the exceptions listed in §21.3 marked **`AUDIT-DRIVEN CORRECTION (V4)`**. Inside Part II, *"this gate"*,
> *"this pass"*, *"this report"*, *"this file"*, *"V1"*, *"V2"* and *"V3"* refer to the **V3 authoring gate
> and its documents**, not to the V4 gate. Part II carries V3's own Part I cover, V3's Part II (V2's body) and
> V3's Part III (§20.1–§20.7) unchanged except at the anchors declared in §21.3; V4's own cover is Part I
> above, and V4's own corrections are Part III below (§21.1–§21.7). The `# PRE-3-CORRECTED-V3 …` heading that
> follows is **V3's own title, preserved verbatim**. Part II therefore ends with **V3's own footer** (§20.7 of
> V3); V4's own gates are at the head of this document and in §21.7 (§21.6, DV-8). V3's terminal digest label
> reads `- **V3 SHA-256 …` and the carried V2 label reads `- **SHA-256 …`; neither is selectable by V4's own
> digest rule (§21.5), which keys on the literal `- **V4 SHA-256`.
# PRE-3-CORRECTED-V3 — DESIGN CORRECTION AND RECONCILIATION (THIRD BOUNDED CORRECTION PASS)

**Document type:** Corrected design report (documentation only — NO implementation)
**Work order:** WO-PRE-3-V3-DESIGN-CORRECTION — bounded documentation-only correction of PRE-3 V2
**Mode:** STRICT READ-ONLY REPOSITORY / EXTERNAL REPORT ONLY
**Repository (read-only; not modified by this pass):** `yarem44uk/TACTICAL_CORE` — local path `/opt/data/tactical_core_github`
**Branch:** `main`. **Baseline:** `1f20e9a867ce7d286e6e72a71ddefeec8f7f9264` (re-observed read-only this gate; the remote was never contacted)
**Timestamp:** 2026-10-13 (UTC, container clock; session date)
**Supersedes (as design guidance):** PRE-3 V2, identified in §I.2. V2 is **not** modified, renamed, moved or deleted by this pass. It is preserved **byte-for-byte** at the identity recorded in §I.2 and remains the exact artifact its independent audit addressed.
**New artifact:** yes — one **new, additional** file. V1, V2, the V1 audit, the V2 audit, PRE-1, PRE-2, the current PRE-3 and the previous audit are all preserved unmodified (§I.2, §I.3).

**Authorization gates — unchanged by this pass:**

**Implementation authorization:** NOT GRANTED
**Git commit / push authorization:** NOT GRANTED
**Production deployment authorization:** NOT GRANTED

## Part I — V3 cover: identity, inputs, scope and preservation

### I.1 Purpose of this pass (bounded)

Correct the **three** defects (`C-V2-1`, `C-V2-2`, `C-V2-3`) that the independent audit of V2 identified, and
address the audit's advisory findings (`NV-2`, `NV-4`, `NV-5`, `NV-6`, `NV-7`) where the evidence supports a
precise correction. The task is to produce a new versioned report. **No application code, test, CI job,
configuration, migration or guard is implemented, and nothing is published or deployed.**

Every change made by this pass is labelled **`AUDIT-DRIVEN CORRECTION (V3)`**, and the superseded V2 statement
is named so the audit trail is complete. **No new design decision is taken and no operator decision is taken.**

### I.2 Input identity verification — measured from disk before any edit

| Input | Path | Expected bytes | Measured bytes | Expected SHA-256 | Measured | Result |
|---|---|---|---|---|---|---|
| **V2** (corrected report) | `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V2.md` | `156249` | **156249** | `3721a17e03b5861ffea646a7857a72f8e7a6daf77c14c1aad8c8644dc781e611` | identical | **MATCH** |
| **V2 audit** (independent) | `/opt/data/output/PRE-3-CORRECTED-V2-INDEPENDENT-AUDIT.md` | `51456` | **51456** | `15ef2d6398a1f17edb83d097a62c7e0c4942f29e35fe9dbd3ddf6b178177bd41` | identical | **MATCH** |

**2 / 2 MATCH.** Neither input was missing, mismatched, substituted, reconstructed or repaired. **Both were
read in full** before any correction (V2: 1934 content lines plus a final empty line; the V2 audit: 454
content lines). Had either identity failed, this pass would have reported `BLOCKED` and created nothing.
`[SOURCE-CONFIRMED: os.path.getsize + full-file SHA-256, measured outside the repository]`

### I.3 Upstream preservation re-check (re-hashed from disk; not re-read)

| Input | Bytes (measured) | SHA-256 (measured) | Result |
|---|---|---|---|
| V1 (corrected report) | 97686 | `a9418f4f8a3dccaec0dee3cc00b70f8f74c4c3fae92c290eb5c2ca6bc458b328` | **MATCH** to the earlier passes' records |
| V1 audit (independent) | 56724 | `6d64ae5be6f9cee5856c1a1c84feb97672f29ee3515ee77aeba70fe14f9adc72` | **MATCH** to the earlier passes' records |
| PRE-1 | 41034 | `cc7e5647e36192426a9da08d9364b53e1c13239f12d95d1318b63601ae5ffcd4` | **MATCH** to the earlier passes' records |
| PRE-2 | 66793 | `b2d955db05b6c3644ce0f640865f5ccf7e04a54b99375a74077a36a6e812471c` | **MATCH** to the earlier passes' records |
| PRE-3 (current) | 68327 | `2d1bd878117fa48cf83824622387829b55d63209bfc3cfddf74fe01bd00cfb46` | **MATCH** to the earlier passes' records |
| previous audit | 77918 | `1d4a2503916b452535ac5b722a68ed23c63afa78113b0c3a74e1f09b55d2a4a2` | **MATCH** to the earlier passes' records |

**6 / 6 reproduce the identities fixed by the earlier passes**, and all six were **re-hashed after the
V3 write and are unchanged** (§20.5). This pass altered no earlier artifact.

### I.4 Relationship to V2 (what is preserved, what is corrected)

**Preserved.** V2 is carried forward in Part II as the body of this report. The **only** V2 regions this pass
rewrites are the **twenty-two** anchors listed in §20.3, each a direct response to a named audit finding.
**Every technical conclusion, evidence boundary, source citation, table, test specification, open-decision
record and authorization restriction of V2 that is not listed in §20.3 is carried forward byte-identically.**

**Corrected.** §20.1 maps each audit correction and advisory item to the V3 section that resolves it, the
basis on which it was verified in this pass, and its status. The three work-order-required corrections are
`C-V2-1` (LOW-6 typography and footer), `C-V2-2` (PC-01/PC-02 cross-reference provenance) and `C-V2-3`
(structural-guard AST call-form coverage).

**Consequence for the V1-to-V2 preservation chain (disclosed, §20.6 DV-9).** Two of the thirteen V1
line-ranges that the V2 audit verified as byte-identical in V2 (V1 lines 215–260 and V1 lines 459–488)
contain text this pass was **required** to change (NV-5 at V1 lines 238–240; C-V2-3 at V1 lines 477 and
480). Those two blocks are therefore **not** reproduced verbatim in V3. The other **eleven** blocks are
byte-identical. See §20.6 DV-9/DV-10.

**Disambiguation that governs all of Part II.** Inside Part II, the self-referential expressions *"this
gate"*, *"this pass"*, *"this report"*, *"this file"*, *"V1"* and *"V2"* refer to **V2 and its authoring
gate** — not to the V3 gate. Part II is quoted material preserved as evidence about V2. Where a V3 correction
touches a Part II passage, that passage carries an explicit **`AUDIT-DRIVEN CORRECTION (V3)`** marker.

### I.5 Claim-tag legend

| Tag | Meaning |
|---|---|
| **SOURCE-CONFIRMED** | Read directly by the gate named in the passage, from the committed tree at `1f20e9a` or from third-party library source, with `path:line` given. In Part II this tag therefore means "confirmed **by V2**". |
| **AUDIT-CONFIRMED** | Asserted by an independent audit and carried because re-derivation was outside the reading scope of the gate carrying it. |
| **DESIGN-RECOMMENDATION** | Proposed design. *Not implemented.* |
| **OPERATOR-DECISION** | Cannot be derived from the repository. Requires the operator. |
| **UNVERIFIED** | Runtime, deployment or process fact not established by a read-only gate. |
| **AUDIT-DRIVEN CORRECTION** | A statement changed in direct response to an audit finding. The superseded statement is named. |
| **SOURCE-BYTE FACT** | A conclusion derived from a hexadecimal dump or an exact byte/list comparison of the file on disk — never from visually rendered text (§I.6). |
| **INTERPRETATION** | A reading of evidence (typography, markdown rendering, reachability) that is not itself a byte fact. |

### I.6 Reading completeness, method, and the rendering-artifact warning

- **V2:** read in **full** (1934 content lines plus a final empty line) before any correction.
- **V2 audit:** read in **full** (454 content lines), including its §4 (PC-05), §5 (C-3 / PT-16), §6 (secret
  inventory), §7 (V1-to-V2 preservation), §9 (reconciliation), §10 (§10.1 NV-1…NV-7 and §10.2 BYPASS-1), §11
  (repository state) and §13 (required corrections).
- **Repository and third-party source were NOT re-read by this pass.** This work order authorises reading the
  two named report files only. Every source citation in Part II is therefore carried as V2's statement
  (`SOURCE-CONFIRMED` **by V2**) and is **not** re-asserted as `SOURCE-CONFIRMED` by V3. **No new source claim
  is made anywhere in this document.**
- **Rendering-artifact warning (material to C-V2-1 and to every quotation in Part III).** This gate's own
  tool output **distorts asterisk runs and some adjacent words** — for example the byte string
  `authorization:** NOT GRANTED` can be displayed with a spurious extra asterisk, and `NOT GRANTED.` can be
  displayed as `NOT ***`. The independent audit of V2 disclosed the same class of artifact as its DV-4, and it
  plausibly explains the inherited LOW-6 error. **Consequently every asterisk-bearing or quotation-critical
  conclusion in this report rests on a hexadecimal dump or an exact `str.count` / list comparison of the file
  bytes — never on rendered text** (§5.25, §20.2).

### I.7 Scope limits of this pass (what V3 does not do)

1. **No implementation.** No code, test, CI step, workflow, configuration, migration, guard, redactor or
   logging change is written, or claimed to exist. The `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` status
   of every design item in Part II is unchanged.
2. **No re-derivation of Part II's source evidence** (see §I.6, §20.6 DV-3). V3 carries V2's citations and
   does not upgrade them.
3. **No operator decision.** `D-1`, `D-2`, `D-3` and `D-4` remain **OPEN** (§20.4). Nothing in V3 selects a
   migration branch, a target platform profile, a runtime/test contract, or a percent-encoding policy.
4. **No acceptance of itself.** V3 contains no `ACCEPTED`, `VERIFIED IMPLEMENTATION` or `PRODUCTION READY`
   verdict. It is offered for independent re-audit pinned to its stored-file SHA-256, which is reported in the
   terminal response and **not** embedded here (§20.5).
5. **No Git mutation, no remote contact, no publication, no deployment** (§20.6, §20.7).

---

## Part II — Carried-forward V2 body

> **Disambiguation banner — governs all of Part II.** Part II is **V2 content preserved as evidence**, with
> the exceptions listed in §20.3 marked **`AUDIT-DRIVEN CORRECTION (V3)`**. Inside Part II, *"this gate"*,
> *"this pass"*, *"this report"*, *"this file"*, *"V1"* and *"V2"* refer to the **V2 authoring gate and its
> documents**, not to the V3 gate. In particular, the V2 §17 integrity record's byte count (`156249`) and its
> series digest identify **V2's bytes**; V3's own identity record is §20.5 and V3 embeds no digest of itself.
> The `# PRE-3-CORRECTED-V2 …` heading that follows is **V2's own title, preserved verbatim**. V2 §19.3's
> cross-reference to a "§0" was a dangling reference inside V2 (§20.6, DV-8); the list of sections carried
> into this document is §I.4.

# PRE-3-CORRECTED-V2 — DESIGN CORRECTION AND RECONCILIATION (SECOND BOUNDED CORRECTION PASS)

**Document type:** Corrected design report (documentation only — NO implementation)
**Work order:** WO-PRE-3-CORRECTED-FIX — Bounded design report correction
**Mode:** STRICT READ-ONLY REPOSITORY / EXTERNAL REPORT ONLY
**Repository:** `yarem44uk/TACTICAL_CORE` (local path `/opt/data/tactical_core_github`)
**Remote (metadata only, not contacted):** `git@github.com:yarem44uk/TACTICAL_CORE.git`
**Branch:** `main`
**Baseline (re-established this gate, no fetch):** `1f20e9a867ce7d286e6e72a71ddefeec8f7f9264`
**Timestamp:** 2026-10-13 (UTC, container clock; session date)
**Supersedes (as design guidance):** the V1 corrected report identified in §2.1. V1 is **not** modified or
deleted by this pass; it is preserved byte-for-byte and remains the audited artifact it was.
**New artifact:** yes — this is a **new, additional** file. PRE-1, PRE-2, the current PRE-3, the previous
independent audit, V1 and the V1 audit are all preserved unmodified (§2, §18.5).
**Implementation authorization:** NOT GRANTED
**Git commit / push authorization:** NOT GRANTED
**Production deployment authorization:** NOT GRANTED

**Purpose of this pass (bounded).** Correct the **three** defects found by the independent audit of V1
(`MED-1`, `MED-2`, `MED-3` — restated in the work order as `C-1`, `C-2`, `C-3`), resolve or explicitly
retain the six advisory **LOW** findings and **LOW-UNVERIFIED**, and otherwise **preserve V1's valid
design content and traceability verbatim**. V2 is therefore "V1 plus bounded corrections", not a rewrite.

**Every change made by this pass is labelled `AUDIT-DRIVEN CORRECTION`.** Where a V1 statement is
corrected, the correction **supersedes** it and the superseded statement is identified so the audit trail
is complete. No new design decision is taken; no operator decision is taken.

**Relationship to V1 (what is preserved).** V1's §1 (purpose/scope/exclusions), §5.1–§5.2, §5.4–§5.17,
§6.1, §6.3, §6.4, §6.6, §7 (all of it), §9.1, §9.2, §9.3, §9.5, §9.6, §10, §11, §13, §14 and §16 are
carried forward **verbatim**. The sections this pass rewrites in whole or in part are: front matter,
§2, §3, §4, §5.3, §5.18–§5.25 (new), §6.2, §6.5, §8, §9.4, §12, §15, §17, §18 and §19 (new). A V2
reader therefore has V1's endorsed content plus the corrections, in one document.

**Claim-tag legend (unchanged from V1, plus one tag).**

**Claim-tag legend (used on every substantive claim).**

| Tag | Meaning |
|---|---|
| **SOURCE-CONFIRMED** | Read by *this* gate directly from the committed tree at `1f20e9a`, or from third-party library source, with `path:line` given. |
| **AUDIT-CONFIRMED** | Asserted by the independent audit (or PRE-1/PRE-2) and re-checked cheaply here, or carried because re-derivation is outside this work order's scope. |
| **DESIGN-RECOMMENDATION** | Proposed by this corrected design. *Not implemented.* |
| **OPERATOR-DECISION** | Cannot be derived from the repository. Requires the operator. |
| **UNVERIFIED** | Runtime, deployment or process fact this read-only gate did not and could not establish. |
| **AUDIT-DRIVEN CORRECTION** | A statement changed in this pass in direct response to an audit finding or condition (MED-1…MED-3, LOW-1…LOW-6, LOW-UNVERIFIED). The superseded V1 statement is named. |

## 1. Purpose, scope and exclusions

### 1.1 Purpose

Reconcile the current PRE-3 design with every finding and condition of the independent audit
`PRE-3-INDEPENDENT-AUDIT.md` (verdict at the time: `ACCEPTED WITH CONDITIONS`), producing a corrected
design in which:

- the structural guard is **satisfiable and discriminating** (H-1);
- the D-3 decision is **truthfully presented** (H-2);
- the secret-handling scope is **closed across the whole disclosure surface** (H-3);
- platform classification, mode provenance, the semantic oracle, the CI pin and the Alembic branches are
  each either finalised or **transparently left to an operator decision**.

### 1.2 In scope

- Reading PRE-1, PRE-2, the current PRE-3 and the independent audit **in full**.
- Read-only inspection of the committed source at baseline `1f20e9a` to validate exact implementation
  boundaries and to re-derive small, cheap measurements (`git grep`, `git show HEAD:<path>`, `git ls-files`).
- Producing this one external report.

### 1.3 Explicitly out of scope (not performed, not authorised)

No repository modification of any kind (source, tests, CI, migrations, dependencies, configuration,
documentation, lockfiles, generated files, bytecode). No helper or temporary file inside the repository.
No execution of application modules, tests, migrations or database operations. No database creation,
opening or connection. No package installation. No environment-variable modification. No lock, IPC
mechanism, broker, writer service or ownership implementation. No commit, push, fetch, pull, checkout,
switch, merge, rebase, reset, clean, stash or `git add`. No network access to the remote. No operator
decision.

### 1.4 What this report is not

It is **not** an independent acceptance verdict. It never uses `ACCEPTED`, `VERIFIED IMPLEMENTATION` or
`PRODUCTION READY`. It does not decide D-1, D-2 or D-3. It does not re-audit PRE-1/PRE-2 and does not
re-audit the prior WO-096…WO-100 series.

---

## 2. Input provenance and hash verification

All identities below were measured **directly from disk** (byte count + full-file SHA-256) **before** any
substantive work, in this gate, outside the repository. Nothing was taken from a prior report's claim.

### 2.1 Authoritative inputs for THIS pass

| Input | Path | Expected bytes | Measured bytes | Expected SHA-256 | Measured | Result |
|---|---|---|---|---|---|---|
| **V1** (corrected report) | `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION.md` | `97686` | **97686** | `a9418f4f8a3dccaec0dee3cc00b70f8f74c4c3fae92c290eb5c2ca6bc458b328` | identical | **MATCH** |
| **V1 audit** (independent) | `/opt/data/output/PRE-3-CORRECTED-INDEPENDENT-AUDIT.md` | `56724` | **56724** | `6d64ae5be6f9cee5856c1a1c84feb97672f29ee3515ee77aeba70fe14f9adc72` | identical | **MATCH** |

**2 / 2 MATCH.** Neither input was missing, mismatched, reconstructed, substituted or repaired. Both were
read **in full** before correction (V1: 1278 content lines; the audit: 647 content lines).
`[SOURCE-CONFIRMED: os.path.getsize + full-file SHA-256, outside the repository]`

Had either identity failed, this pass would have reported `BLOCKED` and stopped. It did not.

### 2.2 Upstream inputs — preservation re-check (identities fixed by the V1 audit)

V1's §2.1 and the V1 audit's §1.2 both record these four as **MATCH**. This gate did **not** re-read them
in full (outside the bounded scope) but **re-hashed them from disk** to confirm this pass altered nothing
and that the V1 audit's identity table is reproducible today. `[SOURCE-CONFIRMED: fresh full-file SHA-256]`

| Input | Path | Bytes (measured) | SHA-256 (measured) | Result |
|---|---|---|---|---|
| PRE-1 | `/opt/data/output/PRE-1-ABSOLUTE-DATABASE-PATH-AND-VALIDATION-DESIGN.md` | 41034 | `cc7e5647e36192426a9da08d9364b53e1c13239f12d95d1318b63601ae5ffcd4` | **MATCH** to V1/audit |
| PRE-2 | `/opt/data/output/PRE-2-INDEPENDENT-AUDIT-OF-PRE-1.md` | 66793 | `b2d955db05b6c3644ce0f640865f5ccf7e04a54b99375a74077a36a6e812471c` | **MATCH** to V1/audit |
| PRE-3 (current) | `/opt/data/output/PRE-3-DESIGN-CORRECTION-AND-RECONCILIATION.md` | 68327 | `2d1bd878117fa48cf83824622387829b55d63209bfc3cfddf74fe01bd00cfb46` | **MATCH** to V1/audit |
| Previous audit | `/opt/data/output/PRE-3-INDEPENDENT-AUDIT.md` | 77918 | `1d4a2503916b452535ac5b722a68ed23c63afa78113b0c3a74e1f09b55d2a4a2` | **MATCH** to V1/audit |

### 2.3 Superseded / non-authoritative variants

The older superseded PRE-3 variant (V1 §2.2) remains **not** an input and was again **not sought,
reconstructed or used**. V1 itself is superseded **as design guidance** by this report but is preserved
**byte-for-byte** at the identity in §2.1 and remains the artifact its audit addressed. **No line of any
superseded variant is used here as evidence.**

### 2.4 Reading completeness (honest statement)

- **V1 audit:** read **in full** (647 lines), including the exact wording of its §7.0 severity table,
  §7.1 (MED-1), §7.2 (MED-2), §7.3 (MED-3), §7.4 (LOW items), §7.5 (UNVERIFIED-1), §7.6, §8 (CI), §9
  (decisions + safety), §10.2 (conditions C-1/C-2/C-3) and §10.4 (its own identity).
- **V1:** read **in full** (1278 lines). All section citations to V1 below are to its actual text.
- **Repository source (explicit paths only, read at `1f20e9a`):** `backend/app/database/migration.py`
  (1–532), `backend/app/database/session.py` (1–376), `backend/app/database/database.py` (1–389),
  `backend/app/operator/entrypoint.py` (40–105), `backend/app/entity_repository/migration.py` (1–14),
  `backend/app/config/database.py` (1–47), `backend/app/config/settings.py` (20–49),
  `backend/app/database/__init__.py` (33–57), `backend/app/telegram_ingress/config.py` (50–89),
  `backend/app/whatsapp_ingress/config.py` (45–84), `backend/main.py` (225–274), `backend/pytest.ini`
  (1–6), `.github/workflows/severity-governance.yml` (15–64).
- **Third-party source (explicit paths, read-only):**
  `.venv/lib/python3.13/site-packages/sqlalchemy/dialects/sqlite/pysqlite.py` (480–660) and
  `.venv/lib/python3.13/site-packages/sqlalchemy/engine/url.py` (620–684, 920–924);
  the package version file reports **SQLAlchemy 2.0.51**.
- **PRE-1 / PRE-2:** **not** re-read in full by this gate (nor were the current PRE-3 or the previous
  audit). As in V1, claims carried from them are tagged `AUDIT-CONFIRMED`, never `SOURCE-CONFIRMED`.

---

## 3. Baseline and worktree safety observations (initial, this gate)

Captured **before** any inspection, with read-only Git plumbing. **No `ls` of the repository root was
executed; no `find`, no `os.walk`, no recursive directory traversal of any kind, no broad glob.**
The protected path was observed **only** as its literal porcelain line.

```
$ git rev-parse --abbrev-ref HEAD            -> main
$ git rev-parse HEAD                         -> 1f20e9a867ce7d286e6e72a71ddefeec8f7f9264
$ git rev-parse refs/heads/main              -> 1f20e9a867ce7d286e6e72a71ddefeec8f7f9264
$ git rev-parse refs/remotes/origin/main     -> 1f20e9a867ce7d286e6e72a71ddefeec8f7f9264
$ git rev-list --left-right --count main...origin/main -> 0   0
$ git diff --cached --name-only | wc -l      -> 0        (zero staged changes)
$ git stash list                             -> (empty — zero stashes)
$ git remote -v                              -> origin git@github.com:yarem44uk/TACTICAL_CORE.git (fetch)
                                                origin git@github.com:yarem44uk/TACTICAL_CORE.git (push)
```

**Baseline: MATCHES the expected `1f20e9a867ce7d286e6e72a71ddefeec8f7f9264` exactly.** `HEAD` = local
`main` = local `refs/remotes/origin/main`. The **remote was not contacted** — no `git ls-remote`, no
fetch, no pull; `origin/main` was read from **existing local Git metadata only**.
`[SOURCE-CONFIRMED]`

**Initial porcelain status — 7 entries, byte-identical to the historical baseline
(`git status --porcelain=v1`):**

```
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500
?? backend/tests/test_wo080_audit_idempotency.py
?? backend/tests/test_wo080_whatsapp_audit_corrective.py
?? docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md
?? docs/work_orders/WO-078-WHATSAPP-INBOUND-HTTPS-ARCHITECTURE-GATE.md
?? docs/work_orders/WO-079-WHATSAPP-INGRESS-ARCHITECTURE-DECISION-GATE.md
```

### 3.1 Precision note on "empty index" (AUDIT-DRIVEN CORRECTION — traceability wording)

V1 and its predecessors record "empty index". That phrase has **two** readings and only one is true:

- **Staging area:** empty — `git diff --cached --name-only | wc -l` = **0**. TRUE.
- **Git index file as a whole:** **not** empty — the index holds **793 tracked entries**
  (`git ls-files --stage | wc -l` = 793). FALSE as a description of the index file.

V2 therefore states explicitly: *the staging area is empty; the index tracks 793 files.* This removes a
recurring ambiguity in the series without changing any historical fact.

Both pre-existing porcelain categories are **inherited, not caused here**: the tracked `.pyc` modification
is a long-standing hygiene artifact (`.pyc` files are tracked in this repository) and the six untracked
entries are unrelated pre-existing work. **Reported, never restored.** The protected `?? 500` is present
**only** as that porcelain line; it was never opened, read, hashed, stat-ed, traversed, copied, moved or
staged, and its size, inode, mtime and owner were never obtained. **No root listing, no `find`, no
`os.walk`, no broad glob was run at any point in this gate.** `[SOURCE-CONFIRMED]`

Final state and the ordered-list comparison are in §18.

---
## 4. Executive disposition and unresolved operator decisions

### 4.1 Findings of the independent audit of V1, and their disposition in V2

| Audit finding | Meaning | Disposition in V2 | Status |
|---|---|---|---|
| **MED-1** (WO C-1) | V1 §8.1's disclosure inventory was presented as *complete* while omitting `migration.py:103-106` (raw URL into an **in-memory** Alembic config) and `migration.py:144`/`:161` (exception-text loggers), and did not cite the source-confirmed leak mechanism `pysqlite.py:566-573`. | §8 rebuilt: unqualified "complete" **withdrawn**; scoped completeness claim (§8.1); inventory extended to **11 carriers** in four classes, incl. the two named and the wider exception-text class (§8.2); compliant controls inventoried (§8.3); third-party mechanism proven **and bounded**, with an explicit **negative finding** for SQLAlchemy 2.0.51 (§8.4); redaction strategy for propagated third-party exceptions (§8.5); tests **ST-09…ST-13** added (§8.8). | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** |
| **MED-2** (WO C-2) | V1's `session.py:167` mismatch set wrongly included **V7**; the correct set is **{V3, V5, V6}**. | §9.4 rewritten; mismatch set corrected to **{V3, V5, V6}** at every occurrence (§5.19, §9.4, §12 PT-11, §15); V7's library-internal disagreement retained as a **separate** point; classification mismatch distinguished from pooling behaviour. | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** |
| **MED-3** (WO C-3) | V1's L3 allow-list target `migration.py:424` (and `:393`) sit **inside the `env_py_content` triple-quoted template** (`:389-444`), not live code; an AST scan sees **zero** call nodes and a naive text count yields **2** — so PT-16 could pass vacuously or fail on correct code. | §6.2 L3 row, §6.5, §12 PT-16 / §12.1 rewritten around the **real execution boundary** (`run_migrations` `:486`, `ensure_database_schema` `:506`, `MigrationManager.upgrade` `:147` → `command.upgrade` `:158`); template vs. live path vs. third-party internal explicitly separated; **MT-05…MT-07** added. | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** |
| **LOW-1** | V5 driver-filename key ordering. | §5.20, §9.4: source verified (`pysqlite.py:609-615` sorts keys) and the **explicit dialect output filename** for V5 added. The audit's cited location was not locatable in V1 (see §5.20) — corrected **and qualified**. | **CORRECTED — QUALIFIED** |
| **LOW-2** | PC-08 "three `sqlite://` literals (relative defaults)" wording. | §5.21, §12 PT-20: only `app/config/database.py:17` is a relative default; `:34` and `:42` are prefix-comparison literals. Count of 3 stands. | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-3** | Missing sixth boundary caller `migration.py:529` (dormant). | §5.22, §6.2: the caller is added and "dormant" is **defined by reachability evidence**, not asserted. | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-4** | Two compliant `database_url=<redacted>` `__repr__` sites omitted. | §5.23, §8.3: inventoried as **compliant controls** (the repository's existing SL-4 precedent), with the compliant/vulnerable distinction stated. | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-5** | `create_engine` import at `session.py:18` omitted from an inventory statement. | §5.24, §6.5, §8.2, §12 PT-16: the import is added and an **imported symbol** is distinguished from a **constructor call**. Count of 3 construction sites unchanged. | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-6** | Markdown typography affecting interpretation. | **§5.25 — AUDIT-DRIVEN CORRECTION (V3) / C-V2-1.** V1's front-matter typography is **already balanced** (byte-verified); **no** V2 front-matter byte was changed and V3 does not claim otherwise. The real, byte-confirmed defect is V1's **split footer sentence** (line 1277 ends `authorization:`; line 1278 carries the lone trailing `*`). V2's unsupported "byte-exact" three-asterisk quotation is **withdrawn**, and V2's own footer is corrected in V3 (§20.7). | **CORRECTED — QUALIFIED** |
| **LOW-UNVERIFIED** | V1 §17.2's "no pre-existing artifact before the write" is a process claim about the authoring session. | §5.25, §17.2: recorded as an **author-reported process fact the auditor could not independently verify**; no attempt to reconstruct missing historical filesystem state. | **CORRECTED — QUALIFIED** |

**All ten items were re-verified against source in this gate before correction; none was resolved by
wording alone** — §5.18–§5.25 give the evidence and §19 gives the mapping matrix.

### 4.2 Verdict for THIS report

**VERDICT: `READY FOR INDEPENDENT RE-AUDIT`.**

The rule applied: this verdict is claimed only if **every** audit condition on V1 has been addressed at
**design** level, or transparently left open because it genuinely requires an **operator** decision, with
**no unexplained gap**. In V2:

1. **MED-1, MED-2, MED-3 are each corrected at design level** with source evidence and an explicit
   implementation-unverified status (§4.1, §5.18–§5.19, §6.2, §6.5, §8, §9.4, §12).
2. **LOW-1…LOW-6 and LOW-UNVERIFIED are each dispositioned** with a source-verified basis and one of the
   three permitted statuses — **not** marked resolved merely because wording changed.
3. **D-1, D-2, D-3 and D-4 remain OPEN** and are neither decided nor implied (§4.4). Their openness is the
   *reason* that PT-15/PT-16's predicate form cannot be frozen — a genuine operator dependency, disclosed
   as such rather than papered over.

This is **not** an acceptance verdict and **not** an implementation authorisation. It says only: *the
bounded correction task is complete and the artifact is fit to be independently re-audited.*

**What an independent re-auditor should specifically try to falsify** — stated so the claim is
challengeable rather than rhetorical: (a) that PC-03/PC-04/PC-05 reproduce from the dialect source at
2.0.51; (b) that **{V3, V5, V6}** is complete, i.e. that every other vector's `session.py:167` predicate
outcome equals its oracle class; (c) that **no** live `engine_from_config` call node exists outside the
template string; (d) that the expanded §8.2 inventory has no omitted **direct** emission site in
`backend/app` + `backend/main.py`; (e) that V1's preserved sections were in fact preserved verbatim;
(f) that D-1…D-4 are still undecided.

### 4.3 What this pass changed relative to V1 (one line each)

1. **Secret surface re-scoped and extended** — "complete" withdrawn, 11 carriers inventoried, the
   in-memory-config and exception-text classes added, and the third-party mechanism proven *and bounded*
   (MED-1 / C-1).
2. **`session.py:167` mismatch set corrected to {V3, V5, V6}** everywhere, with V7's library-internal
   disagreement retained as a separate, narrower point (MED-2 / C-2).
3. **L3 / PT-16 rebuilt on the real execution boundary**, with template vs. live vs. third-party separated
   and three new mutation tests (MED-3 / C-3).
4. **Six advisory LOW items** corrected or explicitly qualified; **LOW-UNVERIFIED** recorded as an
   author-reported process claim (§4.1).
5. **Ambiguity removed** from "empty index" (§3.1) and from the stale path `backend/config/database.py`
   (§5.21).
6. **Traceability completed** with a correction matrix (§19) mapping every audit finding and condition to
   its V2 section and status, alongside the retained V1 matrix (§15).

### 4.4 Unresolved operator decisions (all four remain OPEN — none decided, none implied)

| ID | Decision | Why it blocks | Status |
|---|---|---|---|
| **D-1** | Is the dormant versioned Alembic path intended to become live (Branch A vs Branch B)? | Determines whether `app/database/migration.py`'s Alembic path joins the allow-list or stays in the must-not-be-reached set, PT-16's L3 predicate and expected permitted live-call count, and whether schema-ownership work must precede the gate. | **OPEN / BLOCKED** |
| **D-2** | Target host OS and the deployment `PLATFORM_PROFILE` in {`posix`, `windows`}. | Determines the platform-foreign predicate, PT-14's expected values, and the CI runner pin. | **OPEN / BLOCKED** |
| **D-3** | Mode-provenance option (O1 / O2 / O4; O3 disallowed). | Determines test-migration cost, residual risk, **and the structural guard's invariant form** (argument invariant vs. env-derivation invariant). | **OPEN** |
| **D-4** | Percent-encoded database component: refuse in production, or accept with the literal-filename consequence documented? | Changes PT-12's expected value only. | **OPEN** |

**No decision is taken on the operator's behalf. Every recommendation in V2 is labelled
`DESIGN-RECOMMENDATION`, including V1's carried recommendations.**

---



## 5. Finding-by-finding response to every audit H / M / L item

Statuses follow the work order's vocabulary: `DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED`, `PARTIALLY
ADDRESSED`, `OPEN`, `BLOCKED`.

### 5.1 H-1 — PT-16 / class-C guard unsatisfiable and non-discriminating

**Audit finding (accepted).** The guard as written forbids `create_engine`, `engine_from_config` and
`sqlite3.connect` across `backend/app` + `backend/main.py`, but the canonical boundary itself calls
`create_engine` three times and one application module calls `sqlite3.connect`. Evidence re-verified this
gate with `git grep`: **exactly three `create_engine` construction sites in application code**
(`app/database/session.py:168`, `:175`, `:188`); **exactly one `engine_from_config` construction site**
(`app/database/migration.py:424`); **exactly one `sqlite3.connect`**
(`app/entity_repository/migration.py:9`). Every other `create_engine` hit is a docstring asserting that no
second engine is created, or a test.
`[SOURCE-CONFIRMED: git grep -nE 'create_engine|engine_from_config|sqlite3\.connect' over backend + backend/main.py]`

**Correction:** §6 defines a **narrow, explicit allow-list** with a per-list validation invariant, an
approved-site vs. new-site distinction, positive tests per permitted site, and a negative mutation test
injecting a violation **outside** every allow-list. The guard's stated limits (relocation, aliasing,
imports, alternative constructor forms) are enumerated in §6.6.

**Partial disagreement with AC-AUD-1, with evidence (stated explicitly, not silently overridden).**
**AUDIT-DRIVEN CORRECTION (V3) — advisory NV-5.** V2 presented AC-AUD-1's rule inside **quotation marks**.
The independent audit of V2 identifies that rendering as a **condensation**, not the source's verbatim text:
it adds "exactly", the brace notation and the three construction forms. **The quotation form is therefore
withdrawn, and the passage is restated as an explicit paraphrase — not a quotation:**
The paraphrase reads: the modules permitted to construct an engine/connection are {`app/database/session.py`}
(plus `app/database/migration.py` only under Branch B), and any `create_engine` / `engine_from_config` /
`sqlite3.connect` outside that allow-list is a failure.
The AC-AUD-1 source wording lives in `PRE-3-INDEPENDENT-AUDIT.md`, a document this work order does not
authorise this gate to re-read, so the condensation finding is carried as an **`AUDIT-CONFIRMED`** fact and
**not** as `SOURCE-CONFIRMED`.
Taken literally, that rule **still fails on correct code**, because
`app/entity_repository/migration.py:9` calls `sqlite3.connect` and is not in that allow-list — the same
class of defect H-1 exists to remove. `[SOURCE-CONFIRMED: backend/app/entity_repository/migration.py:3,9]`
The correction is therefore **three allow-lists keyed by construction kind** (§6.2), one of which names
`app/entity_repository/migration.py` explicitly under a **path-form** invariant (a URL validator cannot
guard a bare filesystem path). This **satisfies AC-AUD-1's intent** while removing the residual
unsatisfiability. Status: **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.**

### 5.2 H-2 — D-3 fallback internally inconsistent

**Audit finding (accepted in full).** The PRE-3 §6.4 fallback is offered as the option that avoids the
~90-site test edit, but its sentinel default still raises for every omission, so the cost is not avoided;
and the only reading that *does* avoid the edits — an autouse `conftest.py` fixture injecting a mode —
would neutralise the boundary guarantee for tests.

**Correction:** §7 restates D-3 as **four honest options**, each with runtime-safety semantics, test
migration scope, compatibility impact, failure modes/residual risk and required acceptance criteria. The
false saving is **withdrawn**; the autouse-fixture mechanism is **disallowed as a safety mechanism** and
its weakening is stated concretely. Status: **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.**


### 5.3 H-3 — Secret-handling scope gap

**Audit finding (accepted), and extended.** The audit's inventory of URL-emitting sites in application code
lists **three** sites (`operator/entrypoint.py:79` raw; `session.py:80-87` masked; `database.py:361-367`
masked). V1 found **a fourth** that the audit's §8 inventory does not mention, and a fifth hazard that is
not an emission site but can emit a DSN:

- `app/database/database.py:178` — `"database_url_masked": self._mask_url(str(self.engine.url))` inside
  `DatabaseManager.health_check()` (`:157`), i.e. a URL-derived value placed into a **returned dict**, not
  a log line. Whether any route serialises that dict is **UNVERIFIED**. `[SOURCE-CONFIRMED: database.py:157,173-181,178]`
- `app/database/database.py:183` — `logger.error(f"Database health check failed: {e}")`, plus
  `"error": str(e)` at `:187`. `[SOURCE-CONFIRMED: database.py:182-189]`

**AUDIT-DRIVEN CORRECTION (MED-1 / WO C-1).** The independent audit of V1 found that V1's §8.1 claim to
have reconciled the **complete** surface was itself incomplete: `app/database/migration.py:103-106`
(`set_main_option("sqlalchemy.url", self.database_url)` — the raw URL placed into an **in-memory** Alembic
configuration) and `app/database/migration.py:144` / `:161` (exception-text loggers) were absent, and V1
did not cite the source-confirmed mechanism by which a third-party exception can carry a connection string
(`pysqlite.py:566-573`). That finding is **accepted**. §8 has therefore been rebuilt:

- the unqualified "complete" claim is **withdrawn** and replaced by an explicitly **scoped** completeness
  claim (§8.1);
- the inventory is extended from six entries to **eleven carriers in four classes** — direct emissions,
  in-memory configuration objects, exception-text carriers, and persistent configuration writes (§8.2);
- in-memory configuration is **distinguished** from a persistent configuration-file write (§8.2, §8.5);
- the third-party exception mechanism is **proven from source and bounded**, including an explicit
  **negative finding** for the pinned library version (§8.4);
- a redaction strategy for **propagated third-party exceptions** is specified (§8.5), and tests
  **ST-09…ST-13** cover the required cases (§8.8).

**No claim is made that any logging or redaction fix exists in code.** Status: **DESIGN ADDRESSED —
IMPLEMENTATION UNVERIFIED.**



### 5.4 M-1 — Platform gate has no detection predicate; UNC has no disposition

**Accepted.** §9.3 defines a mode-independent, target-profile-parameterised
`classify_platform_form()` predicate, explicitly disqualifies `os.path.isabs` as the classifier, states the
ambiguity of a leading `//` and the drive-letter form, and defines fail-closed behaviour for ambiguous
forms. The dev-mode asymmetry the audit flagged is **removed by construction**: the platform gate is
mode-independent, so a drive-letter-shaped path is refused in **both** modes rather than accepted as a
relative path in development. Status: **DESIGN ADDRESSED — expected values BLOCKED on D-2.**

### 5.5 M-2 — Presence-of-mode ≠ derivation-of-mode

**Accepted.** §9.5 separates **provenance** from **presence**: a mode supplied by an arbitrary caller as a
string literal is **not** trusted evidence that development is safe in production. One canonical closed
vocabulary with explicit precedence is defined; production rejects development-only bypasses; and the
structural rule is extended to forbid a **string-literal mode** at production entrypoints, backed by a
per-entrypoint runtime assertion and an AST rule. Status: **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.**

### 5.6 M-3 — PT-11 is a consistency test, not a correctness test

**Accepted, and sharpened.** Parity with `session.py:167` is not merely insufficient — it would import that
predicate's defect. §9.4 defines an **independent oracle** grounded in the pysqlite dialect's own
`create_connect_args` source and in SQLAlchemy's documented valid SQLite URL forms, with test vectors whose
expected classification is documented **before** the implementation is consulted. §9.4 also records that
SQLAlchemy's own helpers (`_is_url_file_db` vs. `create_connect_args`) **disagree with each other** on some
URI rows, so the oracle cannot be "whatever the library says" either. Status: **DESIGN ADDRESSED —
IMPLEMENTATION UNVERIFIED.**

### 5.7 M-4 — CI design omits runner OS and Python pin

**Accepted.** §10.3 pins the runner OS and interpreter conditionally, states the `isabs`-dependent
consequence, and — because D-2 is unresolved — **marks the final runner choice `BLOCKED` pending D-2**,
splitting the new tests into platform-independent and platform-specific modules so that only the latter
depends on the decision. Status: **PARTIALLY ADDRESSED — BLOCKED on D-2 for the frozen value.**

### 5.8 M-5 — Alembic branch contradiction

**Accepted.** §11 restates the two branches as **mutually exclusive conditional alternatives**: only their
**intersection** is mandatory until D-1 is answered; each branch's design applies only if the operator
selects it. The contradictory sentence "unless the operator decides, both sets … are mandatory" is
withdrawn and replaced. Implementation is `BLOCKED` pending D-1. Status: **DESIGN ADDRESSED — BLOCKED on D-1.**

### 5.9 L-1 — PT count stated inconsistently (19 vs 20)

**Accepted.** §12 adopts a single authoritative numbering **PT-01…PT-20** and records which of the two
prior statements was wrong (PRE-3 §1.1 row 6 and §3 said `PT-01…PT-19`; §8.3 listed `(PT-20)` and is
correct). PRE-3's §1.1/§3 text is superseded for count purposes.

### 5.10 L-2 — Line-citation drift

**Accepted and re-measured this gate.** Corrections: the `alembic.ini` **write is `migration.py:384`**
(`:385` is `logger.info(f"Created {alembic_ini}")`, which contains the *path*, not the URL —
`[SOURCE-CONFIRMED: migration.py:384,385]`); **`init_alembic` is defined at `migration.py:322`** (not
`:337`), with the ini template at `:344-383` and `sqlalchemy.url` at `:348`; the Alembic env template
starts at `:389` with the `engine_from_config` import at `:393` and the construction inside
`run_migrations_online` (`:422`) at `:424-428`. `[SOURCE-CONFIRMED]`

### 5.11 L-3 — Class-D reacher list not exhaustive

**Accepted.** §6.4 adds `app/composition.py`'s `*.initialize()` reachers to class D. Verified this gate:
`composition.py:549`, `:585`, `:597`, `:722`, `:744`, `:817` each call an `initialize()` that reaches a
`Base.metadata.create_all` site; `:612` is carried as `AUDIT-CONFIRMED` (listed by the audit, not re-read
here). `[SOURCE-CONFIRMED for the six re-read]`

### 5.12 L-4 — Work-order citation drift (not a PRE-3 defect)

**Accepted.** `backend/app/database/entity_repository/migration.py` **does not exist**; the real path is
`backend/app/entity_repository/migration.py`. Verified this gate: `git ls-files --error-unmatch` returns
TRACKED for the latter and NOT TRACKED for the former. `[SOURCE-CONFIRMED]` **This report does not repeat
the erroneous path as if valid anywhere except in this explicit correction, in the audit's own L-4
quotation, and in the traceability matrix's audit-ID column.**

### 5.13 L-5 — PRE-3 §0.3's "no root listing" is an unverifiable process claim

**Accepted.** §18 of this report makes **only** claims about its own session that are supported by the
operations it can list, and tags as **UNVERIFIED** anything about *PRE-3's* authoring session. This gate
executed **no** `ls` of the repository root, **no** `find`, and **no** `os.walk`, and therefore **has no
deviation to disclose and no traversal to defend**.

### 5.14 L-6 — §7.1(2) rule stricter than §7.2's "correct use"

**Accepted.** §8.4 resolves it explicitly: the normative rule (`never emit more than the sanitised
scheme/driver in production`) governs, and **all four** URL-derived sites must change — the two
previously-endorsed "masked" sites included. PRE-3 §7.2's endorsement of `session.py:83` and
`database.py:364` as "correct use" is **withdrawn** as inconsistent with §7.1(2).

### 5.15 L-7 — Cost figures hedged but exact

**Accepted.** §7 uses the exact measured figures without hedging: **90 occurrences of
`configure_session_manager(` across 39 test files**, **21 occurrences of `DatabaseSessionManager(` across 12
test files**, **1 occurrence of `initialize_database(` in 1 test file**, **3 test files containing
`DATABASE_URL`**. Re-measured this gate with `git grep` and **identical to the audit's measurements**.
`[SOURCE-CONFIRMED]`

### 5.16 L-8 — Percent-encoded row disposes ACCEPT without stating the risk

**Accepted and escalated into D-4.** §9.6 states the operator-visible consequence (the literal `%20` string
is handed to the driver, so the on-disk filename contains literal percent characters; no decoding occurs;
an encoded separator is **not** a separator) and proposes a **stricter production disposition (`REFUSE`)**
as a design choice, with PRE-3's `ACCEPT` retained as the alternative. Because the two dispositions change
PT-12's expected value, the choice is recorded as **D-4**, not decided here.

### 5.17 L-DEV — Disclosure of protected-path and probe deviations

**Accepted as recorded by the audit; not repeated here.** This gate discloses its **own** deviations in
§18.4. It performed no repository-root traversal and did not stat or size the protected object.

---

### 5.18 MED-1 (WO C-1) — secret-disclosure inventory and the exception mechanism

**Audit requirement (its exact meaning preserved).** §8.1's disclosure inventory is presented as complete
while omitting two URL-carrying sites — `migration.py:103-106` (raw URL into the in-memory Alembic config)
and `migration.py:144`/`:161` (exception-text loggers) — and does not cite `pysqlite.py:566-573`, which
formats the URL into a raised `ArgumentError`. Required either to extend §8.1 to **all** URL-carrying and
DSN-emitting sites with a per-site disposition, or to scope §8.1 explicitly and add a named subsection for
"config-object and exception-text carriers". Silent omission is the only unacceptable option. An ST test
must drive a malformed URL through the migration module and assert that **no substring of the URL** appears
in the emitted text.

**Independent re-verification (this gate).**
`migration.py:93-112` read verbatim: when `self._alembic_config is None`, an `AlembicConfig` is constructed
at `:100-102` and `self._alembic_config.set_main_option("sqlalchemy.url", self.database_url)` runs at
`:103-106`. **CONFIRMED — the raw URL string enters an in-memory config object.**
`migration.py:143-145` and `:160-162` read verbatim: `logger.error(f"Failed to create migration: {e}")`
at `:144`; `logger.error(f"Database upgrade failed: {e}")` at `:161`. **CONFIRMED.**
`pysqlite.py:565-573` read verbatim: `raise exc.ArgumentError("Invalid SQLite URL: %s\n" "Valid SQLite URL
forms are:\n" … % (url,))`. **CONFIRMED — the dialect formats the URL into the exception text.**
`[SOURCE-CONFIRMED]`

**Correction.** §8 rebuilt as described in §5.3; the mechanism is cited and **bounded** in §8.4.

**Additional source-confirmed findings made by this gate (not raised by the audit; disclosed as such).**
The exception-text carrier is **not** limited to two lines — the same construct appears at
`migration.py:178`, `:193`, `:237`, `:252`, `:267`, `:286`, `:317`/`:318`; `database.py:137`, `:229`; and
`session.py:266-275` (`:272`, `"error": str(e)` inside the always-executed rollback path). All are
inventoried in §8.2 with per-site dispositions. A **negative** finding is also recorded: SQLAlchemy
2.0.51's URL-parse failure says only `"Could not parse SQLAlchemy URL from given URL string"`
(`url.py:920-924`) and does **not** echo the input — so that particular path is **not** an exposure in the
pinned version, and V2 does not claim it is (§8.4).

**Status: DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.** The load-bearing test is ST-09/ST-10 (§8.8).

### 5.19 MED-2 (WO C-2) — the `session.py:167` mismatch set

**Audit requirement.** The mismatch set is **{V3, V5, V6}**, not `{V3, V5, V6, V7}`; correct **all**
occurrences; reassess every derived table, count, conclusion and test expectation; preserve the broader
finding that memory detection must be evaluated against the selected oracle; distinguish a classification
mismatch from downstream pooling/session behaviour; preserve the V7 `_is_url_file_db` vs.
`create_connect_args` observation; keep connection/pooling consequences as **design implications** unless
directly proven by source; execute nothing.

**Independent re-verification (this gate).** The predicate is `session.py:167`:
`if ":memory:" in self.database_url:` — a **bare substring test on the whole URL string**
`[SOURCE-CONFIRMED]`. Evaluating it against the oracle classes of V1 §9.4:

| # | URL | Substring `:memory:` present? | Predicate branch | Oracle class | Agreement |
|---|---|---|---|---|---|
| V3 | `sqlite://` | no | FILE branch (`QueuePool`) | MEMORY | **MISMATCH** |
| V4 | `sqlite:///:memory:` | yes | MEMORY branch (`StaticPool`) | MEMORY | agree |
| V5 | `sqlite:///file:memdb?mode=memory&cache=shared&uri=true` | no (no literal `:memory:`) | FILE branch | MEMORY | **MISMATCH** |
| V6 | `sqlite:///file::memory:?cache=shared` (no `uri`) | yes (`file::memory:`) | MEMORY branch | FILE | **MISMATCH** |
| V7 | `sqlite:////file:memdb1?mode=memory&cache=shared` (no `uri`) | no | FILE branch | FILE | **AGREE — not a mismatch** |

**Corrected set: `{V3, V5, V6}`. V1's inclusion of V7 was wrong**; V1's sentence "says MEMORY for V6 and
V7" is superseded (it says MEMORY for **V6** only; for V7 it says FILE, which coincides with the oracle).

**Occurrences corrected in V2:** §4.1 (MED-2 row), §9.4's parity clause and pooling sentence, §12 PT-11,
§15 (PC-04/PC-05 rows). **Retained as a separate point:** V7's **library-internal** disagreement —
`_is_url_file_db` (`pysqlite.py:492-498`) inspects `url.query.get("mode")` **irrespective of the `uri`
flag**, so it returns `False` for V7 ("not a file db"), while `create_connect_args` (`:616-619`) builds the
abspath'd filename `/file:memdb1` — a file; as a consequence `check_same_thread = not
_is_url_file_db(url)` (`:621-623`) is `True` for that file-backed URL. `[SOURCE-CONFIRMED]`

**Honest boundary (audit requirement 4/6).** What is corrected is a **classification** statement about a
predicate. The **pooling consequence** (`session.py:167` → `:168-185`) is a **design implication**: a
`create_engine` call was never made and no connection was opened by this gate, so no runtime pooling
behaviour is claimed.

**Status: DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.**

### 5.20 LOW-1 — V5 driver-filename key ordering

**Audit requirement.** The pysqlite dialect sorts the relevant keys; verify the cited source around
`pysqlite.py:609-615` and correct any order-sensitive expected representation, preserving semantic equality
where order is not meaningful.

**Independent re-verification (this gate).** `pysqlite.py:594-615` read verbatim: when `uri` is truthy the
dialect copies the query, **pops every pysqlite-driver key** (`:605-606`), takes `filename = url.database`
and appends `"?" + "&".join("%s=%s" % (key, uri_opts[key]) for key in sorted(uri_opts))`, with the source
comment `# sorting of keys is for unit test support` (`:609-615`). **CONFIRMED: the output key order is
SORTED.** For V5 the popped set includes `uri`, so the driver filename is
`file:memdb?cache=shared&mode=memory`. `[SOURCE-CONFIRMED]`

**Locating the audit's citation.** V1 was scanned for the unsorted form `…?mode=memory&cache=shared`. It
occurs in V1 **only as part of the input URL strings** of V5 and V7 (V1 §9.4 vector rows; §9.2 prose) —
never as an expected *output*. V1's V5 row stated the class only (`MEMORY (named, shared)`) and gave no
filename, so no order-sensitive **expected value** existed to correct, and the audit's cited location could
not be located in V1.

**Correction.** V2 §9.4 now states V5's dialect-derived driver filename explicitly **in sorted order**, and
records that the query order inside a URL string is **input syntax**, not an expected output — so no
order-sensitive representation required changing. Semantic equality is preserved: the class is MEMORY
either way.

**Status: CORRECTED — QUALIFIED** (source confirmed; the cited representation was not present in V1 to
change, so the correction is an added explicit expected value plus a qualification).

### 5.21 LOW-2 — PC-08 "three `sqlite://` literals" wording

**Audit requirement.** Only `app/config/database.py:17` is a relative default; `:34` and `:42` are
prefix-comparison literals. The count (3) is correct; the wording is not.

**Independent re-verification (this gate).** `backend/app/config/database.py` read verbatim:
`:17` `url: str = "sqlite:///./storage/database/tactical_core.db"` — **a relative default**;
`:34` `valid_prefixes = ("sqlite:///", "postgresql://", "mysql://", "mssql://")` — **a prefix-comparison
literal**; `:42` `return self.url.startswith("sqlite:///")` — **a prefix-comparison literal**.
Exactly three `sqlite:///` literals. `[SOURCE-CONFIRMED]`

**Path drift in the work order (disclosed, not repeated as valid).** The work order's LOW-2 text cites
`backend/config/database.py:17`. That path is **NOT tracked** (`git ls-files --error-unmatch` fails); the
real, tracked path is **`backend/app/config/database.py`**. V2 uses the real path.

**Correction.** §12 PT-20 now states: **one relative default (`:17`)** and **two prefix-comparison literals
(`:34`, `:42`)**. The dead-config conclusion is unchanged and remains supported: no import of
`app.config.database` exists outside the `app/config` package, so the module stays unreferenced.

**Status: CORRECTED — SOURCE CONFIRMED.**

### 5.22 LOW-3 — the additional dormant `initialize_database` caller

**Audit requirement.** V1's "four live entrypoint paths" omits a non-test caller of `initialize_database`
at `migration.py:529`; add it to the caller inventory, explain "dormant" from **actual reachability
evidence**, and **do not** treat absence of a known entrypoint as proof of impossibility.

**Independent re-verification (this gate, `git grep` over tracked files bounded to `backend`).**
Call sites in **non-test application code**:

| Caller form | Sites | Count |
|---|---|---|
| `initialize_database(` | `main.py:243`, `telegram_ingress/app.py:154`, `whatsapp_ingress/app.py:162`, **`migration.py:529`** | **4** |
| `configure_session_manager(` | `database.py:352` (intra-package), `operator/entrypoint.py:78` | **2** |

⇒ **six boundary call sites: five live + one dormant** (`migration.py:529`). This reconciles V1's "four
live entrypoint paths" with the audit's six. `[SOURCE-CONFIRMED]`

**Reachability evidence for "dormant".** `ensure_database_schema` (def `:506`) has **no non-test caller** —
only its by-name re-export at `app/database/__init__.py:47` and its `__all__` entry at `:82`.
`run_migrations` (def `:486`) is called only from `ensure_database_schema:526`. `init_alembic` (def `:322`)
has **no** caller. `MigrationManager` is instantiated only at `:499`, inside `run_migrations`.
`[SOURCE-CONFIRMED]`

**Definition of "dormant" (stated, not asserted).** *No non-test application path reaches
`migration.py:529` from any live entrypoint today (`main.py`, the two ingress apps, the operator
entrypoint); it becomes reachable if any module imports the by-name symbol from `app.database` and calls
it.* This is a **reachability statement about the tree at `1f20e9a`**, **not** a claim that the path is
impossible or unreachable in principle — the by-name export exists precisely to make activation
**import-free**, which is why the branch question (D-1) is a gate, and why §11 requires the validator at
both `run_migrations` and `ensure_database_schema` **regardless** of the branch.

**Correction.** §6.2's boundary-entry list, §4.1 and §15 now carry the six-site enumeration.

**Status: CORRECTED — SOURCE CONFIRMED.**

### 5.23 LOW-4 — compliant redacted `__repr__` sites

**Audit requirement.** Two compliant `database_url=<redacted>` `__repr__` sites omitted from V1's §8.1
inventory must be recorded as **compliant controls, not vulnerabilities**, and the distinction explained.

**Independent re-verification (this gate).**
`telegram_ingress/config.py:63-70` — `__repr__` marked `# pragma: no cover - defensive masking`, emitting
`f"port={self.port}, database_url=<redacted>, "` at `:68`.
`whatsapp_ingress/config.py:58-66` — the same construct at `:64`. `[SOURCE-CONFIRMED]`

**Distinction (the audit's point).** A **compliant control** emits a **constant placeholder** whose text
contains no character sequence derived from the input, so no parsing or masking failure can turn it into a
leak. A **redactor that returns its input on failure** (the existing `session.py:101` and `database.py:307`
both do exactly that) can. V2 records these two sites in §8.3 as the repository's **existing precedent for
SL-4**, alongside the non-secret refusal style at `operator/entrypoint.py:53-60` (which names the
**property** — `OPERATOR_HOST` — never its value). `[SOURCE-CONFIRMED]`

**Correction.** §8.3 (Inventory B) added.

**Status: CORRECTED — SOURCE CONFIRMED.**

### 5.24 LOW-5 — the `create_engine` import

**Audit requirement.** V1's statement that "every other `create_engine` hit is a docstring … or a test"
omits the import at `session.py:18`; correct the inventory and distinguish an imported symbol from a
constructor call.

**Independent re-verification (this gate).** `session.py:18` — `from sqlalchemy import create_engine,
Engine` — **CONFIRMED**. The remaining non-test `create_engine` hits are **four docstrings** asserting that
no second engine is created (`entity_relations/sqlalchemy_relation_repository.py:12`,
`entity_repository/sqlalchemy_entity_repository.py:11`, `entity_repository/sqlite_repository.py:18`,
`projection/recovery_health.py:38`) — all re-measured. The three **construction** sites are unchanged
(`session.py:168`, `:175`, `:188`). `[SOURCE-CONFIRMED]`

**Correction.** §6.5, §8.2 and §12 PT-16 now distinguish an **imported symbol** (binds a name; constructs
nothing) from a **constructor call** (creates an engine). The guard must match **call syntax**, not a bare
name — which is also why §6.6 records alias/relocation limits.

**Status: CORRECTED — SOURCE CONFIRMED.**

### 5.25 LOW-6 and LOW-UNVERIFIED

**LOW-6 — Markdown typography.**

**AUDIT-DRIVEN CORRECTION (V3) — C-V2-1.** V2's account of LOW-6 is **withdrawn and restated on the actual
bytes**. Three of its assertions are corrected. The byte facts below were established in this pass by
**hexadecimal dump and exact list comparison** — never by eye — because this environment's console rendering
distorts asterisk runs (§I.6): the same artifact the V2 audit disclosed as its DV-4, and the probable origin
of the inherited error.

*Source-byte facts — `SOURCE-BYTE FACT` (hex-anchored, measured from the files on disk this pass):*

| Object | Byte content (from hex) | Asterisks | Verdict |
|---|---|---|---|
| V1 line 13 | `**Implementation authorization:** NOT GRANTED` | 4 (two balanced pairs) | **already balanced** |
| V1 line 14 | `**Git commit / push authorization:** NOT GRANTED` | 4 (two balanced pairs) | **already balanced** |
| V1 line 15 | `**Production deployment authorization:** NOT GRANTED` | 4 (two balanced pairs) | **already balanced** |
| V2 lines 15—17 | equal, element-by-element, to V1 lines 13—15 (`==` on the two lists: **True**) | 4 each | **carried unchanged; no correction was needed and none was made** |
| V1 line 1277 | `operator decisions **D-1, D-2, D-3 remain OPEN** and **D-4** is newly added. Implementation authorization:` | 8 (four balanced pairs) | **ends `authorization:` — no trailing asterisk** |
| V1 line 1278 | `NOT GRANTED.*` | 1 (one lone trailing `*`) | **byte fact: one trailing `*`; the “unterminated span” reading is withdrawn — it is `INTERPRETATION`, not a byte fact (§20.2 item 7a)** |
| V2 line 1933 | `decisions **D-1, D-2, D-3 and D-4 remain OPEN**. Implementation authorization: NOT GRANTED. Git commit /` | 4 | NOT-GRANTED statement **split across lines** |
| V2 line 1934 | `push authorization: NOT GRANTED. Production deployment authorization: NOT GRANTED.*` | 1 (trailing) | statement **split**; **trailing `*`** |

*Exact hex anchors (measured this pass):*
V1 line 13 = `2a2a496d706c656d656e746174696f6e20617574686f72697a6174696f6e3a2a2a204e4f54204752414e544544`;
V1 line 14 = `2a2a47697420636f6d6d6974202f207075736820617574686f72697a6174696f6e3a2a2a204e4f54204752414e544544`;
V1 line 15 = `2a2a50726f64756374696f6e206465706c6f796d656e7420617574686f72697a6174696f6e3a2a2a204e4f54204752414e544544`;
V2 lines 15/16/17 are **byte-identical** to V1 lines 13/14/15;
V1 line 1277 **ends** `…617574686f72697a6174696f6e3a`; V1 line 1278 = `4e4f54204752414e5445442e2a`.

**What this corrects in V2.**

1. **The "three-asterisk" form did not exist.** V1's front-matter lines 13—15 are `**…:**` — **two** asterisks
   on each side, balanced (four per line). V2's "byte-exact" quotation showing three asterisks is **not
   byte-exact** and is **withdrawn**.
2. **V2's front matter was never corrected, and did not need to be.** V2 lines 15–17 are **byte-identical** to
   V1 lines 13–15 (verified as equal lists, not by eye). V2's claim that, as a *correction*, it writes the
   front-matter line in the form "`**Implementation authorization:** NOT GRANTED` (two asterisks, balanced)" is
   **withdrawn**; the accurate statement is that the front matter was **carried unchanged**.
3. **The real defect is the footer, not the front matter — restated on the bytes (AUDIT-DRIVEN
   CORRECTION (V4) — C-V3-1).** Byte facts measured this pass: (i) the NOT-GRANTED statement is
   **split across V1 lines 1277 and 1278**; (ii) V1 line 1278 ends with **one lone `*`**;
   (iii) the asterisk inventory over V1 lines 1273–1278 is **1 + 8 + 1 = 10**, i.e. **five balanced
   pairs**, in one non-blank-separated paragraph (no blank line occurs between V1 lines 1273 and 1278).
   The footer defect is therefore a **format** defect — a NOT-GRANTED statement split across two
   lines, with a trailing asterisk on the last content line — **not** an unbalanced-emphasis defect.
   *Withdrawn.* V3's earlier reading of that trailing `*` as an **“unterminated emphasis span at end
   of file”**, and its tag of that proposition as `SOURCE-BYTE FACT`-confirmed. The reading is **not
   byte-obtainable**, and the measured inventory argues against it: with ten asterisks in five balanced
   pairs in one unbroken paragraph, the italic span opened on V1 line 1273 **closes** on V1 line 1278, so
   the file's emphasis is **balanced** and only the individual footer *lines* are not self-balanced. The
   proposition is retagged **`INTERPRETATION`** and recorded as withdrawn in §20.2 item 7a. **A trailing
   asterisk alone does not establish an unclosed span.**

**Qualification on the work order's own wording (disclosed deviation, §20.6 DV-6).** The work order states
*"V1 line 1277 contains no asterisks"*. The **bytes** show line 1277 contains **eight** asterisks in four
balanced pairs and **ends** with `authorization:`. The accurate statement is therefore **no asterisk at the end
of line 1277**, with the single trailing `*` on line 1278. V3 records the byte truth rather than the work
order's condensed sentence, and discloses the divergence in §20.6. (The work order's phrasing appears to
condense the V2 audit's own rendering-distorted clause, which displayed `authorization:` with a spurious
asterisk run.)

**Correction applied by V3.**

- V2's **front matter is left byte-identical** — it is the same correctly balanced `**…:**` construction as
  V1's, and no markdown defect exists there.
- **V3's own front matter and footer** (§20.7) use **balanced emphasis** throughout — `**…**` for the three gate lines and single-asterisk `*…*` for the closing italic lines (**AUDIT-DRIVEN CORRECTION (V4) — F-V6**, corrected from an earlier “balanced `**…**` throughout”) — and place **each NOT-GRANTED
  statement on a single line**, and carry **no** trailing or dangling asterisk. Their content does not
  contradict this change log: the front matter's three NOT-GRANTED lines are gates, and §20.7 states that
  nothing in this pass was authorised or performed.
- Legitimate asterisk-bearing content elsewhere — e.g. the redactor replacement pattern `r"\1****\2"` — is
  **untouched**; no unrelated editorial rewriting was performed.

**Status: CORRECTED — QUALIFIED.** The typography defect is real and is now **source-byte-confirmed** (V1's
footer: a split NOT-GRANTED statement plus a lone trailing `*`). The disposition is **qualified** because
(a) V2's stated basis — a three-asterisk front-matter defect — is **not supported by the bytes**, and (b)
V2's front matter was, correctly, **never changed**, so any claim that it was corrected is false and is
withdrawn.

**LOW-UNVERIFIED — output-path pre-existence.** V1 §17.2's "Pre-existing artifact at this path: none
detected before the write" is a **process claim about the authoring session** of V1 and is **not
independently checkable**. This gate **did not** attempt to reconstruct historical filesystem state and
**cannot** verify it. V2 records it as an **author-reported process fact that the auditor could not
independently verify** (the same class as the previous audit's L-5 and the V1 audit's UNVERIFIED-1). What
V2 *can* state, and does, is that its **own** write target did not exist at the time of writing (§17.2) and
that V1 is preserved at the §2.1 identity.

**Status: CORRECTED — QUALIFIED.**



---

## 6. Corrected design: canonical validation boundary and engine-construction allow-list (H-1 / AC-AUD-1)

### 6.1 Why a blanket prohibition cannot work

A rule that forbids construction *sites* must either (a) fail on the correct tree, or (b) be relaxed until
it no longer discriminates. Both outcomes are failures. The corrected rule therefore fixes the
**invariant** — *every permitted construction is preceded by the validation appropriate to its kind* — and
makes the *site list* explicit, narrow and separately testable.


### 6.2 The three allow-lists (approved sites, exact, re-verified this gate)

**AUDIT-DRIVEN CORRECTION (MED-3 / WO C-3) applies to the L3 row and to §6.5.** V1 allow-listed
`app/database/migration.py:424` as a live `engine_from_config` **call site**. It is not one: that line (and
the import at `:393`) lie **inside the triple-quoted `env_py_content` template** (`:389-444`). The row
below therefore states what is *actually* enforceable, and §6.5 states the corrected structural predicate.

| List | Kind | Permitted site(s) | Invariant the site must satisfy |
|---|---|---|---|
| **L1 — engine** | SQLAlchemy `create_engine` **call** | `app/database/session.py:168`, `:175`, `:188` (only) | Each call is reachable **only** through `DatabaseSessionManager.initialize` (`session.py:139`), and the validator runs **before** the branch at `session.py:156` and before the first `create_engine` at `:168`. The module-level import at `session.py:18` is a **binding, not a construction**, and is excluded by matching call syntax (LOW-5). |
| **L2 — raw DBAPI** | `sqlite3.connect` **call** | `app/entity_repository/migration.py:9` (only) | Before `connect`, the **path-form** validator must run on `db_path` (a URL validator cannot guard a bare filesystem path). The function is `apply_migrations` (`:7`) and is **UNREFERENCED** today; it is allow-listed so the guard passes on correct code, and flagged for remediation-or-replacement by the implementation work order (it must not be deleted under K-8). |
| **L3 — Alembic** | `engine_from_config` — **generated template content, NOT a live application call site** | `app/database/migration.py`, inside the `env_py_content = '''…'''` template spanning `:389-444` (import `:393`, construction `:424-428`); the template is written to a generated `env.py` at `:445` | **Branch B:** validator + fail-closed mode resolution at the entry of `run_migrations` (`:486`) **and** `ensure_database_schema` (`:506`), before any Alembic command runs; the executable construction then happens **inside third-party Alembic**, which an application-module guard cannot statically inspect. **Branch A:** the permitted live-call count in this module is **zero** and the Alembic command path must be **unreached** (§11.1). |

**Boundary entry points (not construction sites, but gated)** — corrected enumeration (LOW-3): every
module in `backend/app` + `backend/main.py` that calls `configure_session_manager`, `initialize_database`
or `DatabaseSessionManager(` must pass a mode resolved from the canonical signal (§9.5), never a string
literal in production code. The **six** boundary call sites at `1f20e9a` are `database.py:352`,
`operator/entrypoint.py:78`, `main.py:243`, `telegram_ingress/app.py:154`, `whatsapp_ingress/app.py:162`
and `migration.py:529` — **five live and one dormant** (`migration.py:529`, dormant per §5.22).
`[SOURCE-CONFIRMED: six call sites, re-measured this gate]`

**Verified boundary reachability (AUDIT-CONFIRMED, re-checked cheaply):**
`DatabaseSessionManager.initialize` is called from exactly one place — `configure_session_manager`
(`session.py:357`) — and `initialize_database` (`database.py:330`) reaches it via
`configure_session_manager` at `:352-355`.
`[SOURCE-CONFIRMED: session.py:349-359; database.py:352]`


### 6.3 The invariant, stated for the implementation work order

> **Scoped invariant.** In `backend/app` + `backend/main.py`: (i) every `create_engine` occurs only in
> `app/database/session.py`, and every occurrence is preceded by the canonical validator inside the same
> call path; (ii) every `sqlite3.connect` occurs only in `app/entity_repository/migration.py` and is
> preceded by the path-form validator; (iii) every `engine_from_config` occurs only in
> `app/database/migration.py` and — **only if Branch B is selected** — is preceded by the validator and the
> fail-closed mode resolution; (iv) any construction of any of these three forms **outside** its list is a
> test failure **and** a CI failure; (v) every schema mutation (`Base.metadata.create_all`) binds an engine
> the boundary already built.

### 6.4 Schema-mutation (class D) sites — completed reacher list

Class D application sites (all bind the boundary-built engine), re-verified this gate:
`app/database/database.py:116` (**LIVE**), `app/database/schema_migration.py:116` and `:365` (**TEST-ONLY**),
`app/projection/checkpoint.py:64`, `app/entity_repository/sqlite_repository.py:73`,
`app/entity_repository/sqlalchemy_entity_repository.py:88`,
`app/entity_relations/sqlalchemy_relation_repository.py:133`,
`app/event_repository/durable/sqlalchemy_event_repository.py:70`,
`app/event_delivery/plugin_idempotency_ledger.py:48`, `app/event_delivery/outbox_repository.py:88`.
`[SOURCE-CONFIRMED: git grep -nE 'metadata\.create_all']`

**Added reachers (L-3 / AC-AUD-4):** `app/composition.py:549,585,597,722,744,817` (six re-read this gate)
and `:612` (`AUDIT-CONFIRMED`). These reach class-D sites through `*.initialize()` calls without passing
through `initialize_database`, so they must be named in the inventory even though they remain
boundary-consistent (they bind the already-built engine or a not-ready global manager).


### 6.5 Approved site vs. new unapproved site, and the exact structural predicate

**AUDIT-DRIVEN CORRECTION (MED-3 / LOW-5).** V1's per-module count rule asserted "exactly one
`engine_from_config`" in `app/database/migration.py`. That assertion is **unsatisfiable by an AST scan**
(the module contains **zero** live `engine_from_config` call nodes) and **wrong for a naive text count**
(the name occurs **twice**, at `:393` and `:424`, both inside the template literal). Superseded.

- **Approved existing site:** a construction at exactly one of the L1/L2 lines, in exactly that module,
  with its invariant satisfied.
- **New unapproved site:** any construction of the guarded forms **not** at a listed line, or an added
  construction **within** a listed module at a new location. Both are failures. A guard keyed only on
  "module is allowed" would miss an added construction inside an allowed module; a guard keyed only on
  "line is allowed" would be brittle against benign reformatting. **The rule is therefore module + call
  count + invariant per module**, with these exact predicates:

| Module | Permitted construction calls | Exact predicate | Basis |
|---|---|---|---|
| `app/database/session.py` | **3** `create_engine` **call** nodes (`:168`, `:175`, `:188`) | AST: `Call(func=Name('create_engine'))` **or** `Call(func=Attribute(attr='create_engine'))` — the bare form and the module-qualified form (`sqlalchemy.create_engine(…)`, `sa.create_engine(…)`) — count == **3** in this module; a **fourth** call node in **either** form fails. The import at `:18` is an `ImportFrom`, not a `Call`, and is excluded by matching **call syntax** (LOW-5). **AUDIT-DRIVEN CORRECTION (V3) — C-V2-3 / BYPASS-1:** the predicate is stated over **both** the `ast.Name` and the `ast.Attribute` call form. Bound: an aliased binding to an unrelated name (`from sqlalchemy import create_engine as ce` → `ce(…)` is `Name('ce')`) is covered **only if** the guard resolves import bindings (§6.6). | SOURCE-CONFIRMED by V2 (count); predicate widened by V3 |
| `app/entity_repository/migration.py` | **1** `sqlite3.connect` **call** node (`:9`) | AST: count == **1** matching `Call(func=Attribute(value=Name('sqlite3'), attr='connect'))` **or** the bare-name form `Call(func=Name('connect'))` (a `from sqlite3 import connect` binding, which an attribute-only predicate would miss). **AUDIT-DRIVEN CORRECTION (V3) — C-V2-3 / BYPASS-1.** | SOURCE-CONFIRMED by V2 (count); predicate widened by V3 |
| `app/database/migration.py` | **0** live `engine_from_config` **call** nodes | The name must occur in `backend/app` + `backend/main.py` **only inside** the `env_py_content` template literal (`migration.py:389-444`), i.e. a whole-package **call-syntax** scan — stated over **both** the `ast.Name` and the `ast.Attribute` form of the name (**AUDIT-DRIVEN CORRECTION (V3) — C-V2-3**, so a module-qualified live call such as `alembic.engine_from_config(…)` is also caught) — yields **zero** live call sites outside that template span. Under Branch A the permitted live-call count is 0; under Branch B the *live* path is the command path in the row below, not a construction in application code. | SOURCE-CONFIRMED by V2 (both textual occurrences are inside the string literal) |
| Alembic live command path (Branch B only) | not a construction site in application code | `run_migrations` (`:486`) → `MigrationManager(...)` (`:499`) → `.upgrade(revision)` (`:503`) → `MigrationManager.upgrade` (`:147`) → `command.upgrade(cfg, revision)` (`:158`); the engine is constructed by Alembic from the generated `env.py`, i.e. **inside third-party code the application-module guard cannot statically inspect** (§6.6). | SOURCE-CONFIRMED |

**No count is asserted for third-party Alembic internals** — the guard cannot see them, and V2 does not
pretend otherwise. `[SOURCE-CONFIRMED: all counts re-measured this gate; see §8.2, §12]`


### 6.6 Negative mutation test and the guard's stated limits

**Proposed negative mutation tests (§12, MT-01…MT-04)** operate on a **temporary copy outside the
repository** (the work order forbids repository writes) and must fail loudly:

- **MT-01** — append `create_engine("sqlite:///x.db")` to a module outside L1 (e.g. a synthetic
  `app/_synthetic_violation.py` in the copy) ⇒ engine guard **fails**.
- **MT-02** — append a fourth `create_engine(...)` inside `app/database/session.py` ⇒ count-based guard
  **fails** (this is the mutation AC-AUD-1 requires to target a site "outside the allow-list" *and* the
  harder case inside an allowed module).
- **MT-03** — append `sqlite3.connect("x.db")` outside L2 ⇒ raw-connect guard **fails**.
- **MT-04** — move the permitted `engine_from_config` call into a new module ⇒ L3 guard **fails** (proves
  relocation detection).

**Guard class and honest limits (must be stated in the implementation work order, not glossed).** A
text/AST-based guard proves **shape**, never runtime behaviour. Specifically it **can** detect: a new
literal call to `create_engine` / `engine_from_config` / `sqlite3.connect`; an aliased import
(`from sqlalchemy import create_engine as ce`) **if** the guard resolves import bindings rather than
matching raw call names; a **module-qualified** call (`sqlalchemy.create_engine(…)`, `sqlite3.connect(…)`) because the §6.5 predicates are stated over **both** the `ast.Name` and the `ast.Attribute` call form (**AUDIT-DRIVEN CORRECTION (V3) — C-V2-3 / BYPASS-1**); and relocation of a permitted call into another module. It **cannot** reliably
detect: fully dynamic construction (`getattr(sqlalchemy, "create_" + "engine")`, `importlib.import_module`,
`eval`, a factory table built at runtime), construction inside a third-party dependency it does not scan, a
call reached through `functools.partial`, a call whose callee is bound to an unrelated local name (`ce = create_engine; ce(…)`) unless the guard resolves import bindings, or a plugin loaded from outside `backend/app`. Those gaps are
closed only by combining the structural guard with the **runtime-path** tests (PT-01/02/05/08/18/19) and by
keeping the boundary refusal absolute regardless of caller — which is why the boundary rule (§9.5) is the
load-bearing control and the guard is the anti-regression net.

**Do not claim the guard is proven.** It is proven only when the mutation tests actually run and fail, in a
separately authorised implementation work order. Today: **not implemented, not proven.**

---

---

## 7. Corrected D-3 decision analysis, with truthful options (H-2 / AC-AUD-5)

### 7.1 Measured cost (re-verified this gate, exact — no hedging)

| Call form in `backend/tests` | Occurrences | Test files | Source |
|---|---|---|---|
| `configure_session_manager(` | **90** | **39** | `git grep -o` / `-l` |
| `DatabaseSessionManager(` | **21** | **12** | `git grep -o` / `-l` |
| `initialize_database(` | **1** | **1** | `git grep -o` / `-l` |
| files containing `DATABASE_URL` | — | **3** (`test_wo032_production_entrypoint.py`, `test_wo080_whatsapp_ingress.py`, `test_wo083_telegram_ingress.py`) | `git grep -l` |

Union upper bound: **112 call sites across up to 52 distinct test files** (files may overlap between the
first two rows; the exact union count is a design-input measurement for the implementing work order, not
asserted here). There is **no `conftest.py` anywhere in the repository** today (verified:
`git ls-files conftest.py` → none), and `backend/pytest.ini` sets **no `pythonpath`** and **no
`DATABASE_URL`** (verified: pytest.ini lines 1-6). `[SOURCE-CONFIRMED]`

### 7.2 The withdrawn claim

PRE-3 §6.4 presented a sentinel default (`mode=_REQUIRED`) as the option that avoids the ~90-site edit
while keeping omission fatal, and described the residual exposure as "a source-level omission". **That is
false on both counts, and this report withdraws it:**

- The sentinel **still raises on every omission**, so **all 112 call sites must be edited anyway**. The
  sentinel does not save one line of work; it only changes the error message.
- "A source-level omission" is **not** residual exposure, because omission raises at the boundary under
  both the required-argument design and the sentinel design. The residual exposure claim does not exist.

### 7.3 Four options, each stated truthfully

**O1 — explicit required mode argument (recommended).**
Runtime safety: maximum. The boundary cannot be reached without a mode; omission is a loud type error at
the call site; production entrypoints derive the mode from the canonical signal (§9.5).
Test migration scope: all 112 call sites edited (mechanical; a codemod plus review), plus a test-visible
declaration of `development`/`test` at each edited site.
Compatibility impact: internal API change to `configure_session_manager`, `initialize_database`,
`DatabaseSessionManager` — no published/external API and no wire protocol is affected.
Failure modes / residual risk: a missed call site fails loudly at collection or first call (good failure
mode); a *wrong* mode literal is the residual risk, and it is closed by O1's companion rule (§9.5: literals
untrusted at production entrypoints + AST rule + runtime assertion). Residual fail-open risk: **none from
omission.**
Acceptance criteria: PT-01/02/04/05/08 (runtime), PT-15/16/17 (structural), MT-01…MT-04 (mutation), and the
§9.5 provenance tests.

**O2 — sentinel default `mode=_REQUIRED`.**
Runtime safety: equivalent to O1 for omission (it raises), with worse diagnostics.
Test migration scope: **identical to O1 — all 112 call sites** (this is the withdrawn claim, restated
truthfully). It saves nothing.
Compatibility impact: identical to O1.
Failure modes / residual risk: identical to O1; the sentinel adds a permissive-looking signature that
invites a future caller to believe omission is handled.
Acceptance criteria: identical to O1. **Recommended only if a signature-compatibility constraint exists —
none was found by this gate.**

**O3 — autouse `conftest.py` fixture injecting a trusted mode. DISALLOWED as a safety mechanism.**
Runtime safety: **weakened, by construction.** The fixture supplies a mode when the call site omits it, so
inside pytest the boundary no longer fails closed on omission; the guarantee then holds only outside pytest.
Test migration scope: nominally zero, but only because the mechanism defeats the property under test.
Compatibility impact: none — that is exactly its danger.
Failure modes / residual risk: PT-15's discriminating power collapses to "a module outside `tests/` passed
no mode"; the design's central claim (the boundary enforces both halves of the guarantee) becomes **untrue
under test**; and a production pytest invocation would inherit the fixture. Residual fail-open risk:
**real and unquantified.**
Acceptance criteria: **none — O3 must not be adopted.** If any fixture-based convenience is wanted, it must
be an **explicit opt-in** (a per-module marker or an explicit `mode=DEV` at each call site) that still
requires an edit at every call site, i.e. it degenerates into O1 with extra machinery.

**O4 — mode derived from the canonical signal at the boundary, plus a per-entrypoint production assertion.**
Runtime safety: high, with a different shape. The boundary takes **no mode argument**; it resolves the mode
from the canonical `ENVIRONMENT` signal (§9.5) with fail-closed behaviour for missing/invalid values, and
**every production entrypoint asserts `mode == production`** before constructing anything (refusal
otherwise).
Test migration scope: **≈0 call-site edits** (the 112 sites keep their current signatures), replaced by:
(i) an explicit `ENVIRONMENT=development` (or `test`) in the test runner configuration/CI env, and (ii) a
declared production assertion at each of the four entrypoints.
Compatibility impact: the 112 call sites are untouched; entrypoints gain a fail-closed assertion; a test
process that forgets to set `ENVIRONMENT` **fails closed loudly** instead of silently running in
development.
Failure modes / residual risk: the residual risk is **entrypoint omission** — an entrypoint that forgets the
production assertion inherits whatever the environment says, so `ENVIRONMENT=development` in a production
unit file would run with development semantics. Mitigations: the S-class AST rule requires **every**
production entrypoint to call the assertion, and a runtime test drives each real entrypoint with a
development signal and asserts refusal. Even so, the residual risk is **larger than O1's** and is
truthfully stated as such.
Acceptance criteria: PT-05 (missing/invalid mode at real entrypoints), a new per-entrypoint
"development-signal refused in production" runtime test, PT-15/16/17 and MT-01…MT-04 reinterpreted for an
env-derived invariant, plus CI proving the test runner's mode declaration is present.

### 7.4 Effect on the structural guard (why D-3 changes a mandatory test)

Under **O1/O2** the structural invariant is an **argument invariant** ("no call to the boundary without an
explicit, non-literal mode"). Under **O4** it is an **env-derivation invariant** ("no production entrypoint
constructs a database without asserting production mode" + "the boundary resolves the mode fail-closed").
These are different, non-substitutable predicates, so the implementation work order **cannot** freeze
PT-15/PT-16 until D-3 is answered. This is the specific reason the verdict is `READY WITH CONDITIONS`
rather than `READY FOR INDEPENDENT AUDIT` (§4.1).

### 7.5 Status

**D-3 remains OPEN.** This report decides nothing. It removes the false option (the sentinel's "saving") and
the unsafe one (O3), leaving three honest choices (O1, O2, O4) with real, quantified trade-offs.

---

---

## 8. Secret-handling threat surface and test design — REBUILT (H-3 / AC-AUD-7 / MED-1 → C-1)

### 8.0 AUDIT-DRIVEN CORRECTION (MED-1 / WO C-1)

V1's §8.1 described the disclosure surface as reconciled **"complete"**. The independent audit showed that
claim to be **false**: two URL-carrying sites (`migration.py:103-106`, `migration.py:144`/`:161`) were
absent, and the source-confirmed mechanism by which a third-party exception can carry a connection string
(`pysqlite.py:566-573`) was not cited. **The unqualified claim is withdrawn.** This section replaces it
with: a **scoped** completeness claim (§8.1); an inventory extended to **eleven carriers in four classes**
(§8.2); the compliant controls recorded separately (§8.3); the third-party mechanism proven **and
bounded**, including an explicit negative finding for the pinned version (§8.4); a redaction strategy for
**propagated third-party exceptions** (§8.5); the canonical redactor specification (§8.6); the normative
rule restated (§8.7); and the required tests, now **ST-01…ST-13** (§8.8).

### 8.1 Scope of the completeness claim (what "complete" is now claimed to mean — and what it is not)

**Claimed:** this inventory is complete **for direct emissions in application code** (`backend/app` +
`backend/main.py`) of a value **derived from a database URL or connection string** — to a log record, a
`extra=` field, a returned/serialised value, an exception message, a CLI line, or a configuration file —
**as identified by explicit source inspection of the named files at `1f20e9a`**.

**Not claimed (explicitly out of the completeness claim):**
1. third-party library internals beyond the specific lines cited in §8.4;
2. messages constructed dynamically (`format`/`%` on values the source does not name) or by plugins
   outside `backend/app`;
3. third-party Alembic internals executing the generated `env.py` (§6.5);
4. values emitted by dependencies, the driver, or the SQLAlchemy engine outside the cited lines;
5. runtime/deployment facts (log sinks, aggregators, retention) — **UNVERIFIED**.

**This is a correction of V1, not a rhetorical hedge:** V1 claimed completeness without bounds and was
wrong within its own stated scope (`backend/app` + `backend/main.py`).

### 8.2 Inventory A — direct emission sites and carriers in application code (expanded)

Class key: **E** = direct emission · **C** = in-memory configuration object · **X** = exception-text
carrier · **W** = persistent configuration write.

| # | Site (re-verified this gate) | Form | Nature | Class | Status |
|---|---|---|---|---|---|
| 1 | `app/operator/entrypoint.py:79` | `logger.info("operator session manager configured: %s", database_url)` | **raw URL string to the log**, emitted *after* `configure_session_manager` at `:78` | E | LIVE — the one unambiguous violation |
| 2 | `app/database/session.py:80-87` (`:83`) | `logger.info(..., extra={"database_url": self._mask_password(database_url)})` | whole URL, **userinfo password masked only** | E | LIVE — every process that builds a session manager |
| 3 | `app/database/database.py:361-367` (`:364`) | `logger.info(..., extra={"url_masked": DatabaseManager._mask_url(database_url)})` | whole URL, **userinfo password masked only** | E | LIVE — `initialize_database` |
| 4 | `app/database/database.py:173-181` (`:178`) | `"database_url_masked": self._mask_url(str(self.engine.url))` returned from `DatabaseManager.health_check()` (`:157`) | URL-derived value in a **returned dict**; no caller of `health_check` found, so serialisation is **UNVERIFIED** | E | LIVE method; exposure UNVERIFIED (PC-01 — a finding of the **V1 audit**, not of this pass; **AUDIT-DRIVEN CORRECTION (V3), NV-7**; V2 wrote "V1's PC-01") |
| 5 | `app/database/database.py:183` / `:187` | `logger.error(f"Database health check failed: {e}")` / `"error": str(e)` | **exception text** | X | LIVE (PC-02 — a finding of the **V1 audit**, not of this pass; **AUDIT-DRIVEN CORRECTION (V3), NV-7**; V2 wrote "V1's PC-02") |
| 6 | `app/database/migration.py:344-383` (`:348`) / `:384` | `sqlalchemy.url = {database_url}` in the `alembic_ini_content` f-string; `alembic_ini.write_text(...)` at `:384` | **cleartext credential-at-rest** in a generated `alembic.ini`; `:385` logs the *path*, not the URL | W | DORMANT (Branch B). No `alembic.ini` exists (`git ls-files` → none) |
| 7 | **`app/database/migration.py:100-112` (`:103-106`)** | `self._alembic_config.set_main_option("sqlalchemy.url", self.database_url)` | **raw URL string into an IN-MEMORY Alembic config object** — no file written | **C** | DORMANT (Branch B). **NEW — the audit's "Unlisted A"; cited by MED-1** |
| 8 | **`app/database/migration.py:144` and `:161`** | `logger.error(f"Failed to create migration: {e}")` / `logger.error(f"Database upgrade failed: {e}")` | **exception text** — the same class as #5 | **X** | DORMANT (Branch B). **NEW — the audit's "Unlisted B"; cited by MED-1** |
| 9 | **`app/database/migration.py:178`, `:193`, `:237`, `:252`, `:267`, `:286`, `:317`/`:318`** | `logger.error(f"…: {e}")` ×7 and `errors.append(str(e))` (`:318`, into a **returned list**) | **exception text** (and one returned value) | **X** | DORMANT (Branch B). **NEW — same-class extension found by this gate** |
| 10 | **`app/database/database.py:137` and `:229`** | `logger.warning(f"Could not import models: {e}")` / `logger.error(f"Failed to get table info for {table_name}: {e}")` | **exception text** | **X** | LIVE. **NEW — same-class extension found by this gate** |
| 11 | **`app/database/session.py:266-275` (`:272`)** | `logger.error("Session rollback due to error", extra={..., "error": str(e), ...})` | **exception text in an `extra=` field**, on the **always-executed rollback path** | **X** | LIVE. **NEW — same-class extension found by this gate** |

`[SOURCE-CONFIRMED: session.py:80-101, 266-275; database.py:137, 157, 173-189, 229, 294-307, 361-367;
migration.py:93-112, 143-145, 160-162, 178, 193, 237, 252, 267, 286, 317-318, 322, 344-348, 384-385;
operator/entrypoint.py:74-79; `git ls-files alembic.ini` → none; `git ls-files backend/migrations/*` →
`backend/migrations/__init__.py`]`

**Why #7 is not equivalent to #6 (work-order requirement 2).** #7 places the URL in a **process-local
Python object** (`alembic.config.Config`); it persists nothing, but it is reachable by any code holding the
config (including the generated `env.py` executed inside third-party Alembic, and any traceback/`repr` of
the config). #6 writes **cleartext bytes to disk**, where the exposure survives the process. Both must be
controlled; they are **not** equivalent and are separated here.

### 8.3 Inventory B — compliant controls (not vulnerabilities)

| Site | Construct | Why it is compliant |
|---|---|---|
| `app/telegram_ingress/config.py:63-70` (`:68`) | `f"port={self.port}, database_url=<redacted>, "` in `__repr__` | **constant placeholder**; contains no input-derived character sequence, so no parsing/masking failure can turn it into a leak. Marked `# pragma: no cover - defensive masking`. (LOW-4) |
| `app/whatsapp_ingress/config.py:58-66` (`:64`) | same construct | same. (LOW-4) |
| `app/operator/entrypoint.py:53-60` | refusal message naming the property **and interpolating the host value** (`OPERATOR_HOST=%r … % host`) | **AUDIT-DRIVEN CORRECTION (V3) — advisory NV-2 (requalified).** This row does **not** exemplify SL-5: the message names the **property** but **does** emit the host **value** via `% host`. No credential is involved — a host is not a secret — but the "names the property, never its value" characterisation is **withdrawn**. The genuine property-only precedents are the adjacent `OPERATOR_PORT must be an integer` message and `main.py:233-239` for `DATABASE_URL`. (Source citation is V2's; not re-read this pass.) |

**Distinction that matters (audit requirement).** These are controls that **cannot fail open**: the
emitted text is a literal. By contrast, a redactor that returns its input **unchanged on no-match**
(currently `session.py:101` and `database.py:307`, both `re.sub`) **can** fail open — which is exactly
what SL-4 forbids and why the canonical redactor in §8.6 must be fail-closed.

### 8.4 The third-party exception-text mechanism — proven and bounded (work-order requirement 3)

**Mechanism (SOURCE-CONFIRMED).**
`pysqlite.py:565-573`: `SQLiteDialect_pysqlite.create_connect_args` **formats the URL into the exception
text** — `raise exc.ArgumentError("Invalid SQLite URL: %s\n" "Valid SQLite URL forms are:\n" "…" % (url,))`.
That exception propagates out of the URL/engine construction path and lands in carriers #5, #8, #9, #10 and
#11 (`f"…: {e}"`, `str(e)`, or a returned dict/list) — **without the application logging code ever naming
the URL**. This is the precise answer to "how can third-party exception text expose connection strings
even if application logging code does not explicitly format the URL?"

**Bound — how much is exposed (SOURCE-CONFIRMED).**
`url.py:630-667`: `URL.render_as_string(hide_password=True)` is what `str()`/`__repr__()` use. It renders
the userinfo password as `***` (the literal three-character mask) — but renders the **username, host, port,
database path and ALL query parameters** (query keys sorted, values **`quote_plus`-encoded** — percent-encoded rather than raw; recoverable, therefore still an exposure).
Consequently:
- a **userinfo password** is *not* exposed by this particular path (SQLAlchemy masks it itself);
- a **secret-bearing query parameter** (`?api_key=`, `?token=`, `?password=`, `?access_token=`) **is
  exposed** — the mask covers only the userinfo password. **AUDIT-DRIVEN CORRECTION (V3) — advisory NV-6:** the rendered value is **`quote_plus`-encoded** (`url.py:663`), not the raw input, so "verbatim" is **withdrawn**; the exposure stands, because percent-decoding recovers it (percent-encoding is not redaction);
- the **database path/filename and host** are exposed;
- a **raw string** URL formatted by application code (carriers #1 and #7) has **no** masking at all, so the
  password is exposed there in full. Masking is a property of the *object* rendering, not of the string.

**Explicit NEGATIVE finding (this gate — a correction of an assumption, disclosed).**
`url.py:920-924`: SQLAlchemy 2.0.51's URL-parse failure message is only
`"Could not parse SQLAlchemy URL from given URL string"` — it does **not** echo the input string. In
older SQLAlchemy releases that message embedded the raw string (`… from string '%s'`). **V2 therefore does
not claim** that a parse-failure path leaks the URL in the pinned version; the source says otherwise.

**Not claimed.** That generic DBAPI/driver exceptions embed a credential-bearing URL in the general case.
No connection, engine or database was created by this gate, so the runtime contents of driver exceptions
remain **UNVERIFIED**; the mechanism above is the one proven from source.

### 8.5 Redaction strategy for propagated third-party exceptions and diagnostics (requirement 4)

- **SL-8 (new).** A third-party exception must **never** be emitted by raw interpolation of the URL, and
  must never be emitted with its message passed through unchanged. The boundary provides a wrapper that
  (i) never receives the URL as a formatting argument, (ii) reduces a propagated exception to its **type**
  plus a **fixed, non-secret code**, and (iii) if free text is genuinely required for a diagnostic, passes
  it through the canonical redactor (§8.6) with a **fail-closed** fallback. Emitting `str(e)` for a
  database-construction exception is prohibited (carriers #5, #8–#11).
- **SL-9 (new).** **Refuse before construct.** The boundary must classify and validate the URL and resolve
  the mode **before** any engine, session manager or Alembic config is created, so that the dialect's
  `ArgumentError` (`pysqlite.py:566-573`), the config write (`migration.py:384`), and the in-memory config
  population (`migration.py:103-106`) are never reached with a URL the boundary has not already approved.
  The refusal message names the **property** and the **reason**, never the input (SL-5).
- **SL-10 (new).** The in-memory Alembic configuration (#7) must be populated from a **non-persisted**
  channel, and the persistent write (#6) must not occur on any runtime path. If Branch B requires a config
  file, the credential must be supplied by an environment-indirect mechanism agreed in a **separate work
  order**, and the file must be created with no cleartext credential (§11.2, item [B]).

### 8.6 Canonical redactor (one implementation; updated for the expanded surface)

- **One implementation**, in `app/database/` (already the canonical database boundary), with **no second
  copy**; the two legacy helpers (`session.py:89-101` `_mask_password`, `database.py:294-307` `_mask_url`)
  are removed or become thin delegates in the same work order. `[DESIGN-RECOMMENDATION]`
  *(Verified byte-identical this gate: both use `pattern = r"(://[^:]+:)[^@]+(@"` → `r"\1****\2"`, and
  both use `re.sub`, which returns the input **unchanged on no match**.)* `[SOURCE-CONFIRMED]`
- The redactor must handle, uniformly, both a **string** and a parsed URL: a **userinfo password**; a
  **secret-bearing query parameter** (allow/deny list by parameter name: `api_key`, `token`, `password`,
  `access_token`, `secret`, `key`, …); a **malformed/unparseable** input (**fixed placeholder**, never the
  input); and an input with **no** recognisable secret (still never the raw URL in production — only the
  sanitised scheme/driver).
- **Fail-closed, always:** if classification, parsing or masking fails or is uncertain, emit the fixed
  placeholder `"<unparseable>"` plus the offending **property** name. Returning the original input is
  forbidden.
- Redaction remains **defence in depth, never the control** (SL-7): not emitting at all is the control.

### 8.7 The normative rule (SL-1…SL-10)

- **SL-1** In production a raw URL or credential-bearing connection string is **never** emitted: not to
  logs, not in an `extra=` field, not in an exception message, not in a traceback, not in a CLI line, and
  **not in a returned/serialised dict, list or config object** (carriers #4, #7, #9, #11).
- **SL-2** Only the **sanitised scheme/driver** may be emitted, plus non-sensitive metadata that cannot
  identify a host, path, filename, user, token or parameter value. A bare filename can leak infrastructure
  layout, so "path metadata" defaults to **not emitted**.
- **SL-3** **No** passwords, tokens, keys, or secret-bearing **query parameters** may be emitted.
- **SL-4** **Malformed input follows a fail-closed path**: fixed placeholder + property name only.
  **Returning the original input is forbidden as a fallback.**
- **SL-5** Errors name the **property**, not the value.
- **SL-6** The rule applies to **every** carrier in §8.2 — direct emissions, in-memory config, exception
  text, returned values, and the persistent write — not only to log lines.
- **SL-7** Redaction is **defence in depth, never the control.**
- **SL-8** Propagated third-party exceptions are reduced to type + fixed code, or passed through the
  fail-closed redactor; raw `{e}`/`str(e)` for database-construction exceptions is prohibited (§8.5).
- **SL-9** Validate and refuse **before** constructing an engine, session manager or Alembic config
  (§8.5).
- **SL-10** The Alembic URL is supplied by a non-persisted channel and is never written to disk in
  cleartext on a runtime path (§8.5).

**No real credential appears in this report.** No production URL, host, token, query-parameter value or
environment value is quoted; URL forms are shown as inert syntax only.

### 8.8 Required tests — ST-01…ST-13 (each a negative test with a real assertion)

| Test | Asserts |
|---|---|
| ST-01 | Production refusal at each live boundary entry produces a message containing **no** URL, **no** credential and **no** substring of the input URL. |
| ST-02 | A userinfo-password URL produces output in which the password **and** the username are absent. |
| ST-03 | A URL with a **secret-bearing query parameter** (`?api_key=`, `?token=`, `?password=`, `?access_token=`) produces output with that parameter absent — at **every** carrier in §8.2 that can emit it. |
| ST-04 | A **malformed / unclassifiable** URL produces the fixed placeholder and **never** the input string. |
| ST-05 | The **exception-text** path (#5) is driven with a failure whose exception text contains the DSN; the emitted/returned text contains no URL/credential. |
| ST-06 | The **returned-dict** path (#4) is driven and its dict contains no URL beyond the sanitised scheme/driver. |
| ST-07 | **Structural:** the two legacy redaction helpers are gone or delegate to the single canonical implementation (no second copy). |
| ST-08 | Percent-encoded and otherwise unusual values are redacted or refused per SL-4 without echoing the input. |
| **ST-09** | *(WO C-1 requirement)* A **malformed SQLite URL** (SQLite-form violation — `username`/`password`/`host`/`port` present) is driven **through the boundary**, and the emitted text contains **no substring of the URL** — i.e. the dialect's `ArgumentError` text (`pysqlite.py:566-573`) cannot reach a sink. |
| **ST-10** | *(WO C-1 requirement)* **Migration setup and migration failure paths:** with an injected failure at `_get_alembic_config` (`migration.py:100-106`, carrier #7) and at `MigrationManager.upgrade` (`:147-162`, carriers #8/#9), the emitted text contains no URL substring, and the value placed by `set_main_option("sqlalchemy.url", …)` never reaches any log record or returned value. |
| **ST-11** | *(WO C-1 requirement)* **Credential-bearing query parameters** are absent at **every** carrier (extends ST-03 to the expanded inventory, including the exception path and the in-memory config). |
| **ST-12** | *(WO C-1 requirement)* **Malformed-URL redaction failure:** feeding the canonical redactor an input it cannot parse yields the fixed placeholder and never the input; plus a property test that the redactor **never returns its input unchanged** when the input contains a recognised secret-bearing pattern (the fail-open defect of `session.py:101`/`database.py:307`). |
| **ST-13** | *(WO C-1 requirement)* **Persistent Alembic configuration writes:** under Branch A, assert that no `alembic.ini` and no generated `env.py` are written by any runtime path; under Branch B, assert on a temporary copy **outside the repository** that any written config contains **no** credential (carrier #6). |

All thirteen are `DESIGN-RECOMMENDATION`; **none is implemented.** ST-01…ST-08 are carried from V1
(unchanged in substance, re-scoped to the expanded carrier list); ST-09…ST-13 are added by this pass for
WO C-1.

---

## 9. URL/path semantics, platform classification and the independent semantic oracle


### 9.1 Guard order (retained from PRE-3 §5.1, with the platform gate corrected)

```
1. DRIVER-FAMILY GATE    drivername in {sqlite, sqlite+pysqlite}?   no -> NON-FILESYSTEM (never path-validated)
2. SQLITE-FORM GATE      URL carries userinfo/host/port?           yes-> MALFORMED-UNSUPPORTED (SQLAlchemy itself raises)
3. NULL-DATABASE GATE    database is None?                         -> BARE-IN-MEMORY (NOT "malformed" — see 9.4, PC-03)
4. IN-MEMORY GATE        is-memory(database, query, uri)?          yes-> MEMORY (dev/test only; production refuses)
5. URI-FORM GATE         uri-flag truthy or database startswith "file:"? yes -> URI-FORM (explicit disposition)
6. PLATFORM GATE         target-profile classification (9.3)       -> PLATFORM-FOREIGN / PLATFORM-AMBIGUOUS (mode-independent)
7. ABSOLUTE GATE         isabs(database) per TARGET profile?       no -> RELATIVE (production fails closed)
8. CANONICALISE          side-effect-free normpath               -> ACCEPT (canonical)
```

Order remains load-bearing: the driver-family gate must precede everything (a PostgreSQL URL's `database`
is `db`, relative-looking); the SQLite-form gate must precede the `isabs` call (SQLAlchemy raises on
userinfo/host/port, and `isabs(None)` raises `TypeError`); the in-memory gate must precede the absolute
gate (an absolute-looking in-memory database).

### 9.2 Two source-confirmed corrections to the PRE-3 / audit URL tables

This gate read the installed pysqlite dialect source (SQLAlchemy **2.0.51**, the version the repository
pins: `backend/requirements.txt:25` `sqlalchemy>=2.0.0,<2.1`) and its
`SQLiteDialect_pysqlite.create_connect_args`, which is what decides the parameters actually handed to the
driver. It establishes:

- **`sqlite://` (no database) is a documented valid *in-memory* form**, not a malformed URL. The dialect's
  own error text lists the valid forms as `sqlite:///:memory: (or, sqlite://)`, and its code maps a falsy
  database to `":memory:"`. **PRE-3 §5.2 row 3 labels this `MALFORMED`; that label is wrong** (the
  production disposition `REJECT` is nevertheless correct, because in-memory must be refused in production).
  `[SOURCE-CONFIRMED: pysqlite create_connect_args source]`
- **The `uri` query parameter is the *only* thing that enables URI-filename semantics.** When `uri` is not
  truthy, the dialect sets `filename = database or ":memory:"` and then **`os.path.abspath(filename)`** —
  and **drops** unrecognised query parameters (`mode`, `cache` are not in its accepted list). Consequently:
  - `sqlite:///file::memory:?cache=shared` (**no `uri=true`**) → `database = 'file::memory:'` → abspath →
    a **file** named literally `file::memory:` in the process CWD; `cache=shared` is **dropped**. This is
    **not** an in-memory database.
  - `sqlite:////file:memdb1?mode=memory&cache=shared` (**no `uri=true`**) → `database = '/file:memdb1'` →
    abspath → `/file:memdb1`, a **file at the filesystem root**; `mode=memory` and `cache=shared` are
    dropped. This is **not** a named shared-memory database.
  `[SOURCE-CONFIRMED: pysqlite create_connect_args source]`

  **Both the PRE-3 table (§5.2 rows 6 and 6b) and the audit's measured table (§4.3, rows commented
  "in memory") describe these two URLs as in-memory. Under the dialect's own documented semantics they are
  file-backed**, because neither URL enables URI mode. The audit's *measured* columns (`drivername`,
  `database`, `isabs`, substring) are unaffected; only the interpretation is. The production disposition
  (`REJECT`) is unchanged and remains correct; the **dev/test disposition must change from `ACCEPT`**,
  since "accepting" them creates an unintended file (and `/file:memdb1` would require root). **This is a
  stated disagreement with the audit's comment, backed by the dialect source.** `[SOURCE-CONFIRMED]`

  **Honest limit:** this is a reading of library source, not an execution. No connection was opened and no
  file was created by this gate, so the *runtime* outcome is a documented-semantics inference.
  `[UNVERIFIED as a runtime observation]`

### 9.3 Platform classification (M-1 / AC-AUD-6) — mode-independent and profile-parameterised

**Design decisions:**

1. **Classification is mode-independent.** The platform gate refuses the same forms in development, test and
   production. This removes the asymmetry the audit flagged (a drive-letter-shaped POSIX relative path being
   refused in development while ordinary relative paths are accepted there) **by construction**: the refusal
   is not a mode consequence, it is a form consequence.
2. **`os.path.isabs` is disqualified as the classifier.** `os.path` follows the **host**, not the declared
   deployment target. The design uses `posixpath.isabs` or `ntpath.isabs` **explicitly**, selected by an
   operator-declared `PLATFORM_PROFILE ∈ {posix, windows}`. This makes the target OS an explicit,
   auditable input instead of an accident of the machine the validator happens to run on.
3. **Fail closed on profile/host mismatch.** If the declared profile disagrees with the running host
   (`os.name` / `sys.platform`), startup refuses. This matters because the dialect itself calls
   `os.path.abspath` on the **host's** semantics, so a host/target mismatch silently produces a different
   path than the validator approved.
4. **Detection predicate (profile = posix), applied after the driver-family and SQLite-form gates:**

   | Form | Predicate | Class | Disposition (both modes) |
   |---|---|---|---|
   | drive-letter | `^[A-Za-z]:[\\/]` or `^[A-Za-z]:$` on the database component | `PLATFORM-FOREIGN` | **REFUSE** |
   | UNC / double-leading-slash | `database.startswith("//")` | `PLATFORM-AMBIGUOUS` | **REFUSE** |
   | backslash-led | `database.startswith("\\")` | `PLATFORM-FOREIGN` | **REFUSE** |
   | otherwise | — | proceed to the absolute gate | per row |

   **The ambiguity is stated, not hidden:** on POSIX a leading `//` is *implementation-defined*, and
   `os.path.isabs('//server/share/x')` is `True`, so a genuine POSIX absolute path beginning with `//` is
   indistinguishable **lexically** from a UNC path. The design therefore **refuses** `//`-prefixed forms
   rather than guessing. That is a deliberate, documented narrowing (POSIX discourages leading `//`); the
   cost is that a legitimate double-slash POSIX path must be rewritten to a single slash — an
   operator-visible, low-frequency constraint.
5. **Profile = windows** (only if the operator selects it): drive-letter and UNC become legitimate; the
   classifier uses `ntpath.isabs`; a POSIX-style `/srv/x.db` becomes `PLATFORM-FOREIGN` (root-relative
   without a drive). **No Windows or UNC support is claimed today** — the repository establishes no target,
   and this gate found no deployment artifact (see §11.2/D-2).
6. **Nothing is claimed as cross-platform-accepted** until D-2 is answered **and** profile-specific tests
   exist.

### 9.4 The independent semantic oracle (M-3 / AC-AUD-3) — with the mismatch set corrected (MED-2 / C-2)

**Requirement.** PT-11 must not compare two predicates that may share the same error. The oracle below is
derived from (a) SQLAlchemy's documented valid SQLite URL forms as quoted in the dialect's own error text
(`pysqlite.py:570`), and (b) the pysqlite dialect's `create_connect_args` source — **not** from the
implementation under test and **not** from parity with `session.py:167`.
`[SOURCE-CONFIRMED: `pysqlite.py:565-625`]`

**Oracle definition.** `runtime_form(url)` in {MEMORY, FILE, NON_SQLITE, MALFORMED} is decided by what
`create_connect_args` will hand to the driver:

- `NON_SQLITE` — `drivername` not in the sqlite family.
- `MALFORMED` — SQLite URL carrying username/password/host/port (the dialect raises `ArgumentError`), or an
  `uri` value that is not a parseable boolean.
- `MEMORY` — the resulting filename is `":memory:"`, **or** URI mode is enabled (`uri=true`) and the URI
  selects memory (`mode=memory`, or `file::memory:`).
- `FILE` — every other SQLite form: filename = `database` (abspath'd against CWD when URI mode is off).

**Independently-documented test vectors (expected values fixed *before* consulting the implementation):**

| # | URL | Oracle expectation | Basis |
|---|---|---|---|
| V1 | `sqlite:////srv/tc/db.sqlite` | **FILE**, database `/srv/tc/db.sqlite`, absolute | dialect: no uri → filename = database (already absolute) |
| V2 | `sqlite:///rel.db` | **FILE**, relative at parse level; dialect abspaths against **CWD** | dialect `os.path.abspath` branch |
| V3 | `sqlite://` | **MEMORY** (bare form) | dialect maps falsy database → `":memory:"`; error text lists `sqlite://` as valid |
| V4 | `sqlite:///:memory:` | **MEMORY** | dialect: filename `":memory:"` |
| V5 | `sqlite:///file:memdb?mode=memory&cache=shared&uri=true` | **MEMORY** (named, shared) | uri enabled + `mode=memory`. **Driver filename (sorted): `file:memdb?cache=shared&mode=memory`** — the dialect pops `uri` and sorts the remaining keys (`pysqlite.py:605-615`, LOW-1) |
| V6 | `sqlite:///file::memory:?cache=shared` (no `uri`) | **FILE** (`file::memory:` in CWD), `cache` dropped | uri **not** enabled → abspath branch |
| V7 | `sqlite:////file:memdb1?mode=memory&cache=shared` (no `uri`) | **FILE** (`/file:memdb1`), URI params dropped | uri **not** enabled → abspath branch |
| V8 | `sqlite:///file:/srv/x.db?uri=true` | **FILE** (URI with an absolute-ish path; host empty) | uri enabled → filename = `file:/srv/x.db` |
| V9 | `sqlite:////srv/tc/my%20db.sqlite` | **FILE**, literal `%20` in the name (no decoding) | no decoding occurs anywhere in the dialect |
| V10 | `sqlite:////srv/tc/db.sqlite?timeout=5` | **FILE**; `timeout` is a driver arg, not a path part | `timeout` in the accepted driver params |
| V11 | `postgresql+psycopg://u:p@h:5432/db` | **NON_SQLITE** | drivername gate |
| V12 | `sqlite://u:p@h/db` | **MALFORMED** | dialect raises for userinfo/host/port (`pysqlite.py:566-573`) |
| V13 | `sqlite:///C:/data/tc.db` | **FILE** on POSIX (relative!); `PLATFORM-FOREIGN` by profile rule | `posixpath.isabs('C:/data/tc.db')` is False; drive-letter predicate fires first |

**Parity clause — CORRECTED (MED-2 / WO C-2).** The parity assertion is **not** "validator ≡
`session.py:167`". It is: *the validator's memory predicate must agree with the oracle on V1–V13, and
`session.py:167`'s detector must be **corrected** in the same work order to agree with the oracle too.*

Reason: `session.py:167` is the bare substring test `":memory:" in self.database_url`, and it
**disagrees with the oracle on exactly V3, V5 and V6**:

- **V3** (`sqlite://`) — the URL contains no literal `:memory:`, so the predicate returns **FILE**; the
  oracle says **MEMORY**. **MISMATCH.**
- **V5** (`…&uri=true` with `mode=memory`) — the URL contains no literal `:memory:`, so the predicate
  returns **FILE**; the oracle says **MEMORY**. **MISMATCH.**
- **V6** (`file::memory:`, no `uri`) — the URL *does* contain `:memory:` (inside `file::memory:`), so the
  predicate returns **MEMORY**; the oracle says **FILE**. **MISMATCH.**
- **V7** (`/file:memdb1?mode=memory&cache=shared`, no `uri`) — **NOT a mismatch.** The URL contains no
  literal `:memory:` substring, so the predicate returns **FILE**, which **agrees** with the oracle's
  **FILE**. The superseded V1 wording ("says MEMORY for V6 and V7") was wrong for V7.

**Corrected mismatch set: `{V3, V5, V6}`.** *(V1 said `{V3, V5, V6, V7}`; superseded and withdrawn.)*

**Retained as a separate point (not a `session.py:167` mismatch).** SQLAlchemy's **own** two helpers
disagree with each other on V7: `_is_url_file_db` (`pysqlite.py:492-498`) inspects
`url.query.get("mode")` **irrespective of the `uri` flag**, so it returns `False` ("not a file db") for
V7, while `create_connect_args` (`:616-619`) builds the abspath'd filename `/file:memdb1` — a file. As a
consequence, `check_same_thread = not _is_url_file_db(url)` (`:621-623`) is `True` for that file-backed
URL. The design therefore defines the oracle by `create_connect_args` (the connect parameters) and
**explicitly declines** to adopt `_is_url_file_db` as the oracle.
`[SOURCE-CONFIRMED: session.py:167; pysqlite.py:492-498, 565-625]`

**Consequence for pooling — classified as a DESIGN IMPLICATION, not an observed behaviour.**
**AUDIT-DRIVEN CORRECTION (V3) — advisory NV-4.** V2's sentence named only **vector V6** and **vector V5**;
the audit found **vector V3** equally mis-selected and omitted. **Vector V3** (`sqlite://`) is classified
**MEMORY** by the oracle of this section, but `session.py:167` returns FILE (the string has no literal
`:memory:`) and therefore places an **in-memory** database on the `QueuePool` branch. All three vectors are now
named.
`session.py:167` selects the pool class (`:168-185`: `StaticPool` on the MEMORY branch, `QueuePool` on the
FILE branch). On the **corrected** set: it chooses `StaticPool` for **vector V6**, which is in fact a **file**
database, and `QueuePool` for **vector V5** and for **vector V3** (`sqlite://`), both of which are in fact
**in-memory** databases. On vector V7 its FILE branch is the *correct* branch for a file, so no
mis-classification arises there from this predicate. Either the predicate is corrected in the same work order,
or the validator is made deliberately inconsistent — the latter is not acceptable, hence **correction is
required**. **No engine was created and no connection was opened**, so the pooling consequences are a
source-derived design implication only and are **not** an observed runtime behaviour.
`[SOURCE-CONFIRMED for the source (by V2); the runtime pooling outcome is UNVERIFIED]`

**LOW-1 qualification.** The dialect's driver filename for V5 is emitted in **sorted** key order
(`pysqlite.py:609-615`, source comment "sorting of keys is for unit test support"). V1 contained no
order-sensitive **expected output** — the unsorted form appears in V1 only inside the *input URL strings*
of V5/V7 — so the correction here is to state the explicit sorted expected filename (row V5 above) rather
than to change a wrong expectation. The query order inside a URL string is input syntax and is
**preserved** (semantic equality: the class is MEMORY either way).



### 9.5 Trusted mode vs. caller-controlled mode (M-2 / AC-AUD-2)

- **One canonical closed vocabulary**, case-normalised after stripping: `production`, `development`,
  `test`. Anything else (including `prod`, `Production` where not normalised, empty, whitespace-only) is
  **invalid** and refuses.
- **Precedence is explicit and single-source.** The canonical signal is `ENVIRONMENT` — the **only**
  deployment-mode signal read anywhere in application code (`migration.py:522`; `APP_ENV` occurs **zero**
  times in `backend/` and `backend/main.py`). `APP_ENV` is **prohibited**; a future rename must be one
  atomic repository-wide change, never an addition. `[SOURCE-CONFIRMED: git grep ENVIRONMENT → 1 hit;
  APP_ENV → 0 hits]`
- **Missing ⇒ refuse. Invalid ⇒ refuse.** No code path defaults to development. The pre-existing fail-open
  branch at `migration.py:522-532` (`if is_production: … else: initialize_database(…)`) must be corrected in
  the **same** work order, because an unset or mistyped `ENVIRONMENT` currently selects the
  schema-auto-creating branch. `[SOURCE-CONFIRMED: migration.py:522-532]`
- **Provenance rule (the M-2 fix).** A mode supplied by an arbitrary caller — in particular a **string
  literal** in a production module — is **not** trusted evidence that development mode is safe. Production
  entrypoints must **derive** the mode from the canonical signal, and:
  - an **AST rule** forbids a string-literal mode in a call to the boundary from any module that is not a
    test or an explicitly-declared development helper, and
  - a **per-entrypoint runtime assertion** refuses to start unless the resolved mode is `production`.
- **Test/development is declared, never inferred**, and is isolated from production behaviour: a test
  process declares its mode explicitly (§7.3, O1/O4), and no production module can inherit it.
- **Keep the dead precedent dead.** `app/config/settings.py:31` (`environment: str = Field(default=
  "development")`), `:38-41` (`is_production`) and `:43-46` (`is_development`) is a second, **dead**
  mode precedent with no importers outside its own package; it must not become the enforcement point
  (PT-20). `[SOURCE-CONFIRMED: settings.py:21-46]`

### 9.6 Percent-encoded forms (L-8 → D-4)

**Operator-visible consequence, stated as the audit requires.** The literal `%20` (and any other
percent-escape) is handed to the driver **undecoded**, so the on-disk filename literally contains the
percent characters (`my%20db.sqlite`, not `my db.sqlite`). An encoded separator (`%2F`) is **not** a path
separator and creates no directory. A percent-encoded component is therefore indistinguishable from an
encoding mistake, and the two possible operator intentions (a literal `%20` filename vs. a mis-encoded
space) produce **different files** with **no error**.

**Design choice (D-4):** refund in production (`REFUSE` — fail closed on a form whose intent cannot be
established), documented `ACCEPT` retained as the alternative. PRE-3 disposes `ACCEPT`; the audit asked only
that the consequence be stated. Either disposition satisfies L-8; the **stricter** one is recommended,
because a silently-different filename is exactly the class of quiet failure this design exists to prevent.
PT-12's expected value depends on D-4.


---

## 10. CI design and OS / Python dependency (M-4 / AC-AUD-8)

### 10.1 Current state — verified, not taken from a report

There is **exactly one** workflow in the repository:
`.github/workflows/severity-governance.yml` (`git ls-files .github/workflows/*` → that file only).
`[SOURCE-CONFIRMED]`

```
:20-22  on: push / pull_request
:24-25  permissions: contents: read
:29     runs-on: ubuntu-latest
:38-41  python-version: "3.11"
:43-47  python -m pip install -r backend/requirements.txt
:49-67  four severity scripts (drift / markdown / release integrity / single-source)
:69-72  python -m pytest -q backend/tests/test_wo037_08_severity_release_integrity.py
:74-79  python -m pytest -q backend/tests/test_wo037_06_severity_classifier.py     env: PYTHONPATH: backend
backend/pytest.ini: testpaths = tests; python_files/classes/functions; addopts = -v --tb=short
                    (NO pythonpath, NO DATABASE_URL — lines 1-6)
```

**No** database, entrypoint, path-policy, mode or structural test runs in CI. The workflow sets
`PYTHONPATH` for **one step only** (`:78-79`). There is **no `conftest.py`** anywhere
(`git ls-files conftest.py` → none). `[SOURCE-CONFIRMED]` **Describing a test in a report creates no CI
coverage; the new enforcement is inert until a workflow actually runs it.**

### 10.2 Required CI design

1. **A dedicated workflow** (not an appendix to the ADR-013 severity hard gate), so a database-path failure
   is unambiguous.
2. **Explicit module paths** for every new test module — never a bare `pytest` that can collect zero tests.
3. **A collected-node-ID equality assertion** — run `--collect-only -q` and assert the expected node-ID
   **set** (equality, not `>= 1`), so a renamed, moved or emptied module **fails** instead of passing
   vacuously.
4. **`PYTHONPATH` set on every relevant step** (or a committed `pytest.ini` `pythonpath`), because
   `backend/pytest.ini` currently provides none and the existing workflow sets it for one step only.
5. **A mutation step** — copy the tree to a temporary location **outside** the repository, inject the MT-01…
   MT-04 violations, and assert the structural guards **fail**. Without it, the guards are unproven.
6. **Path triggers** — run on any change to `backend/app/**`, `backend/main.py`, `backend/tests/**`,
   `backend/pytest.ini`, `backend/requirements.txt` and the workflow itself, so a future entrypoint or
   migration path is gated automatically.
7. **Whole-package AST property**, so a new direct construction trips the gate without anyone editing a
   file list.

### 10.3 Runner OS and interpreter pin — BLOCKED pending D-2

| Item | Value | Status |
|---|---|---|
| Python interpreter | **pin `3.13`** to match the only verified environment (`/opt/data/tactical_core_github/.venv`, Python 3.13.5) | DESIGN-RECOMMENDATION |
| Requirements install | `backend/requirements.txt` (as today; SQLAlchemy pin `>=2.0.0,<2.1`, FastAPI `>=0.141.0,<0.142`) | SOURCE-CONFIRMED |
| Runner OS | `ubuntu-24.04`-style **POSIX** runner **if** `PLATFORM_PROFILE = posix`; a Windows runner **only** if the operator selects `windows` | **BLOCKED pending D-2** |

**Why the pin is not cosmetic.** The existing workflow is `ubuntu-latest` / Python **3.11** while the local
verification environment is **3.13**, and `os.path.isabs` is host-dependent. PT-14's expected value, and
every `isabs`-dependent assertion, are **undefined in CI** without the pin. Consequently the new tests are
**split**:

- **Platform-independent module(s):** driver-family gate, SQLite-form gate, in-memory set, URI-form set,
  percent-encoding, query orthogonality, redaction/secret tests, mode vocabulary, structural guards, mutation
  tests. These run on any POSIX runner and are **not** D-2-dependent.
- **Platform-specific module:** `PLATFORM-FOREIGN` / `PLATFORM-AMBIGUOUS` classification and PT-14. This
  module is **skipped or failed-explicitly** until D-2 fixes its expected values — never silently passing.

---

---

## 11. Mutually exclusive Alembic Branch A / Branch B (M-5 / AC-AUD-6)

**Corrected framing.** The PRE-3 §10 preamble ("unless the operator decides, both sets … are mandatory") is
**withdrawn** as self-contradictory. The corrected statement is:

> Until D-1 is answered, the **intersection** of the two branches' requirements is mandatory (the items
> labelled **[I]** below). Each branch's remaining items apply **only if the operator selects that branch**.
> Implementation is **BLOCKED** until D-1 is answered.

### 11.1 Branch A — Alembic remains intentionally inactive (applies only if selected)

- **[I]** The by-name re-export at `app/database/__init__.py:43-48` (`MigrationManager`, `init_alembic`,
  `run_migrations`, `ensure_database_schema`) makes activation import-free; the validator is therefore
  required at **both** `run_migrations` (`migration.py:486`) **and** `ensure_database_schema` (`:506`)
  regardless of the branch, so an accidental activation is validated anyway. Enforcement, not discipline.
  `[SOURCE-CONFIRMED: __init__.py:43-48]`
- **[A]** Controls preventing accidental activation: the structural guard treats `engine_from_config` as
  **outside** the allow-list under Branch A (i.e. any occurrence is a failure, and the permitted count for
  `app/database/migration.py` is **zero**); runtime startup must not call `init_alembic`, `run_migrations`,
  `ensure_database_schema` or `MigrationManager.upgrade`; migration configuration must not be created at
  runtime.
- **[A]** Detection of an unexpected active migration path: (i) the L3 structural rule above; (ii) an
  **activation canary** — no `alembic.ini` exists and `backend/migrations/` holds only a tracked 0-byte
  `__init__.py`, so a canary test fails if either appears; (iii) a structural assertion that
  `run_migrations` / `ensure_database_schema` / `init_alembic` gain **no** caller outside the package
  without declaring a mode; (iv) PT-16's **corrected** L3 predicate over `app/database/migration.py` — the name `engine_from_config` occurs **only inside** the `env_py_content`
  template (`:389-444`) and nowhere else in `backend/app` + `backend/main.py`, i.e. **zero** live call
  nodes; plus the runtime-path test asserting `command.upgrade` (`:158`) is **unreached** when the
  validator refuses (§6.5, §12 PT-16).
- **[A]** Prohibited in runtime startup and migration configuration: creating or writing `alembic.ini`,
  creating `migrations/env.py`, and executing any Alembic command.
- **[A]** The **cleartext credential-at-rest** write (`migration.py:348`, written at `:384`) is a
  known, accepted exposure **while dormant**; it must not be created at runtime.
- **Cross-branch note:** the side-effect-free rule for validation (PP-8/T-09b) applies to **the validator
  only**. The Alembic path **does** create files (`:340` `mkdir`, `:384` write, plus a further
  `mkdir`/`touch` pair in the same module); confusing the two remains a trap the plan must state.

### 11.2 Branch B — Alembic becomes active (applies only if selected)

- **[I]** Same re-export/Branch-A intersection items above.
- **[B]** Validation and mode boundary **before migration connection construction**: the validator runs at
  the entry of `run_migrations` (`:486`) and `ensure_database_schema` (`:506`) — provably necessary, because
  `ensure_database_schema:524-526` reaches `engine_from_config:424` **without** `initialize_database` or
  `configure_session_manager`; the mode is resolved through the same fail-closed resolution (the
  `:522-532` branch must be corrected).
- **[B]** Credential handling: the URL must **not** be written into `alembic.ini` in cleartext; if a config
  file is required, the URL must be supplied via a non-persisted channel, and the §8 rule governs any Alembic
  error path.
- **[B]** Schema/migration ownership — a **separate work order**, not this design. Three bring-up
  mechanisms exist today (`Base.metadata.create_all` LIVE at `database.py:116`; Alembic dormant;
  `app/database/schema_migration.py` TEST-ONLY, imported only by tests) and a **single declared owner** must
  be assigned, with the other two explicitly scoped. `[SOURCE-CONFIRMED: the three mechanisms exist]`
- **[B]** New tests: validation-before-engine on the Alembic path; fail-closed mode for
  `ensure_database_schema`; a negative proving the path cannot construct an engine without the validator.

**Neither branch was executed.** No migration was run; no Alembic file was read-modified-written; no
`alembic.ini` exists. `[SOURCE-CONFIRMED: `git ls-files alembic.ini` → none; `git ls-files backend/migrations/*`
→ `backend/migrations/__init__.py` only]`

---

---

## 12. PT-01…PT-20 reconciliation

**Authoritative numbering: PT-01…PT-20** (L-1). Statuses are design statuses, not test results.
**AUDIT-DRIVEN CORRECTIONS (this pass): PT-11, PT-16, PT-17 and PT-20**; MT-05…MT-07 added in §12.1.

| ID | Class | Audit verdict | Corrected specification | Status |
|---|---|---|---|---|
| **PT-01** | U + R | PASS WITH CONDITIONS | Keep both halves; the **R** half must drive the real entrypoint and must **not** monkeypatch the boundary. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-02** | R | PASS | Unchanged; the best-specified test in the set. Add the §9.5 mode-provenance assertion. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-03** | U | PASS | Reframe: `sqlite://` is **BARE-IN-MEMORY**, not `MALFORMED` (PC-03); assert no `TypeError` escapes; production refuses. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-04** | U + R | PASS WITH CONDITIONS | Define the canonical form (`normpath`; **side-effect-free**, no `realpath` that can touch the filesystem) and assert no file is created. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-05** | R | PASS WITH CONDITIONS | Extend to invalid modes (`prod`, `Production`, empty, whitespace) at **all** live boundary entries; assert refusal **before** engine construction. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-06** | U | PASS | Unchanged. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-07** | U | PASS | Unchanged (driver-family branch is a pure function of `drivername`). | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-08** | U + R | PASS | Unchanged; add V3/V5 rows from the oracle (§9.4). | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-09** | U | PASS WITH CONDITIONS | Assert the **disposition**, not merely the class; include the corrected V6/V7 rows (URI mode **not** enabled). | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-10** | U | PASS | **Revised**: the "absolute-looking in-memory" case is V7, which (without `uri=true`) is **file-backed** (PC-04); the genuinely absolute-looking-and-in-memory case requires `uri=true`. Note V7 is **not** a `session.py:167` mismatch (§9.4). | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-11** | U | PASS WITH CONDITIONS | **AUDIT-DRIVEN CORRECTION (MED-2):** correctness against the §9.4 oracle (V1–V13), then parity with the **corrected** `session.py:167`. The `session.py:167` mismatch set is **`{V3, V5, V6}`** — **V7 is excluded** (its predicate already agrees with the oracle). Parity alone is insufficient and explicitly forbidden (M-3). | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-12** | U | PASS | **Revised** per D-4: expected value is `REFUSE` (recommended) or `ACCEPT` with the literal-name assertion; either way assert no decoding. | **OPEN pending D-4** |
| **PT-13** | U | PASS | Unchanged. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-14** | U | **BLOCKED** | **Revised**: mode-independent, profile-parameterised classification per §9.3; expected values fixed only after D-2; runs in the **platform-specific** CI module. | **BLOCKED pending D-2** |
| **PT-15** | S | PASS WITH CONDITIONS | **Revised**: predicate depends on D-3 — under O1/O2 an **argument invariant**; under O4 an **env-derivation invariant**. Must also forbid a **string-literal** mode in production modules (M-2). | **OPEN pending D-3** |
| **PT-16** | S | **FAIL** | **AUDIT-DRIVEN CORRECTION (MED-3 / C-3). Rewritten on the real execution boundary** (§6.2, §6.5). L1/L2 keep exact per-module **call-node** counts (3 and 1) with import lines excluded (LOW-5). The L1/L2 predicates are stated over **both** the `ast.Name` and the `ast.Attribute` call form (`create_engine(…)`, `sqlalchemy.create_engine(…)`, `connect(…)`, `sqlite3.connect(…)`) — **AUDIT-DRIVEN CORRECTION (V3) — C-V2-3 / BYPASS-1**. **L3 is no longer a call-site count:** the predicate is that `engine_from_config` occurs in `backend/app` + `backend/main.py` **only inside** the `env_py_content` template (`migration.py:389-444`), i.e. **zero** live call nodes — an AST "exactly one" assertion is unsatisfiable and a naive text count yields 2; both would be wrong. The **enforceable invariant** is at the entry of `run_migrations` (`:486`) and `ensure_database_schema` (`:506`), and the **load-bearing evidence is the runtime-path test**: with the validator refusing, `command.upgrade` (`:158`) / `MigrationManager.upgrade` (`:147`) and the engine construction inside third-party Alembic must be **unreached**. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-17** | S | PASS WITH CONDITIONS | **Revised**: mutation targets must be **outside** every allow-list **and** include the harder in-module count mutation; **MT-01…MT-07** (§12.1) run on a temporary copy **outside** the repository. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-18** | R | PASS WITH CONDITIONS | **Extended** to query-parameter secrets, malformed URLs, the returned-dict site, the exception-text class and the two migration paths (**ST-01…ST-13**, §8.8). | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-19** | R | PASS WITH CONDITIONS | **Revised**: for the operator, assert "no engine built" only (the `create_all` clause is vacuous for a process that calls only `configure_session_manager`); for P1–P3 assert `create_engine`, the Alembic command path **and** `database.py:116` unreached. Note the dialect may raise during construction for some forms (§9.4 V12). | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |
| **PT-20** | S | PASS WITH CONDITIONS | **Revised (LOW-2)**: needs a precise predicate for "no validation logic added to `app/config/`". `app/config/database.py` contains **three** `sqlite:///` literals — **one relative default (`:17`)** and **two prefix-comparison literals (`:34`, `:42`)** — and the module must stay unreferenced, so this is a **dead-config** guard, not merely a naming convention. | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED |

### 12.1 Proposed negative mutation tests (MT-01…MT-07 — AUDIT-DRIVEN CORRECTION, MED-3 / C-3)

All mutations run on a **temporary copy outside the repository** (the work order forbids repository
writes) and must **fail loudly**.

| ID | Mutation (on the temporary copy) | Must fail | Added by |
|---|---|---|---|
| **MT-01** | Add `create_engine("sqlite:///x.db")` in a module outside L1 | PT-16 engine guard | V1 (satisfies AC-AUD-1's "outside site") |
| **MT-02** | Add a **fourth** `create_engine(...)` inside `app/database/session.py` | PT-16 count/invariant guard | V1 (harder in-module case) |
| **MT-03** | Add `sqlite3.connect("x.db")` outside L2 | PT-16 raw-connect guard | V1 |
| **MT-04** | Relocate the permitted live command path (e.g. move `run_migrations`' body / the `MigrationManager(...).upgrade()` sequence) into a new module | PT-16 L3 live-path guard | V1, **reinterpreted** (the L3 target is template text, not a call site — so what must be detected is relocation of the **live command path**, not of a constructor line) |
| **MT-05** | **Bypass the validation boundary:** remove/disable the validator call at the head of `run_migrations` (`:486`) or `ensure_database_schema` (`:506`) | PT-16 L3 + PT-19 runtime-path guard | **NEW (C-3 requirement 8)** |
| **MT-06** | **Introduce an alternate ungated migration path:** add a module that constructs `MigrationManager(...)` and calls `.upgrade()` directly, or calls `alembic.command.upgrade(...)` on a config built locally, without passing the validator | PT-16 L3 + PT-19 | **NEW (C-3 requirement 8)** |
| **MT-07** | **Live-call-site injection + negative control:** (a) add a *live* `engine_from_config(...)` call **outside** the template in `app/database/migration.py` → must **fail**; (b) edit text **inside** the template only → must **not** fail | PT-16 L3 false-negative **and** false-positive check (the naive-text-count defect) | **NEW (C-3 requirement 8)** |

**These tests are not implemented and the guard is not proven.** They are proven only when they actually
run and fail, in a separately authorised implementation work order.

---

## 13. AC-AUD-1 … AC-AUD-9 reconciliation

| AC ID | Audit requirement (its actual meaning, preserved) | Resolution in this report | Status | Remaining dependency |
|---|---|---|---|---|
| **AC-AUD-1** | Restate PT-16 and the class-C guard as **allow-list + validated-construction invariant**; name the modules permitted to construct; fail on any construction outside; make PT-17's mutation target an outside site. | §6.2 (three allow-lists by construction kind), §6.3 (invariant), §6.5 (approved vs. new; per-module exact counts), §12 (PT-16 rewritten), §12.1 (MT-01…MT-04). **AC-AUD-1's own module list is corrected** (it would still fail on `entity_repository/migration.py:9` — see §5.1). | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | none (D-1 only decides whether `migration.py` is allow-listed or must-not-be-reached) |
| **AC-AUD-2** | Add a requirement and a test that production entrypoints **derive** the mode, not pass a literal. | §9.5 (provenance rule, precedence, AST rule, per-entrypoint runtime assertion), §12 PT-02/PT-15. | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | D-3 changes the invariant's form |
| **AC-AUD-3** | Convert PT-11 to a **correctness** test with explicit expected values, then parity. | §9.4 (independent oracle, V1–V13, documented basis), §12 PT-11; parity target **corrected** to a fixed `session.py:167`. | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | none |
| **AC-AUD-4** | Add `app/composition.py`'s `*.initialize()` callers to class D's reacher list. | §6.4 (`:549,585,597,722,744,817` re-read; `:612` carried). | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | none |
| **AC-AUD-5** | Rewrite §6.4 so the D-3 options are genuinely distinct and the risk statement is truthful; state the concrete mechanism and the exact weakening if an autouse fixture is used. | §7.1–§7.4: the false saving **withdrawn**; O1/O2/O4 with five attributes each; **O3 disallowed** with the weakening stated concretely; D-3 left OPEN. | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | D-3 (operator) |
| **AC-AUD-6** | Define the platform/UNC detection predicate and its dev-mode disposition; restate §10's preamble as the intersection being mandatory until D-1. | §9.3 (mode-independent predicate, `PLATFORM_PROFILE`, `os.path` disqualified, fail-closed ambiguity), §11 (intersection framing, mutual exclusivity). | **DESIGN ADDRESSED — expected values BLOCKED on D-2** | D-2 |
| **AC-AUD-7** | Extend secret handling + tests to sanitised-only logging at **all** emission sites, credential-bearing **query parameters**, and the **malformed-URL** no-fallback rule, with a negative test each. | §8.0–§8.8 (**11 carriers in four classes**, scoped completeness claim, in-memory config distinguished from the persistent write, exception-text mechanism proven and bounded, one canonical redactor, SL-1…SL-10, ST-01…ST-13). | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | none |
| **AC-AUD-8** | Pin the CI runner OS and Python version, and state the `isabs`-dependent consequence. | §10.3: Python pinned (3.13); runner OS **BLOCKED pending D-2**; consequence stated; test modules split platform-independent vs platform-specific. | **PARTIALLY ADDRESSED — BLOCKED on D-2 for the frozen runner value** | D-2 |
| **AC-AUD-9** | Fix the PT-count inconsistency (19 vs 20), the `migration.py:384/385` and `init_alembic:322` line drift, and state the operator-visible consequence of not decoding `%20`. | §5.9 (single numbering PT-01…PT-20), §5.10 (`:384` write, `:385` log, `init_alembic` at `:322`, env template `:389`, construction `:424-428`), §9.6 (`%20` consequence + D-4). | **DESIGN ADDRESSED — the `%20` disposition is OPEN pending D-4** | D-4 |

**Nothing in AC-AUD-1…AC-AUD-9 is marked ACCEPTED.** Every row is a design statement or an open decision.

**AUDIT-DRIVEN CORRECTION index (this pass).** The audit of V1 raised MED-1/MED-2/MED-3 and LOW-1…LOW-6 plus
LOW-UNVERIFIED against V1's handling of the items in this table. Their dispositions and the V2 sections that
resolve them are given in §4.1 and mapped in §19; AC-AUD-7's coverage is widened by §8 and AC-AUD-1's L3
component by §6.2/§6.5, without changing any AC-AUD row's status.


---

## 14. L-1 … L-8 and L-DEV reconciliation

| L ID | Audit finding | Resolution | Status |
|---|---|---|---|
| **L-1** | PT count stated as 19 and as 20 | §12 adopts PT-01…PT-20 as authoritative; PRE-3 §1.1/§3's "PT-01…PT-19" is answered, §8.3 was correct. | RESOLVED (documentation) |
| **L-2** | Line drift: `alembic.ini` write cited `:385` (actually `:384`); `init_alembic` cited `:337` (actually `:322`) | §5.10, §8.1, §11: `:384` write, `:385` log, `init_alembic` `:322`, template `:344-383`, `sqlalchemy.url` `:348`, env template `:389`, `engine_from_config` `:393`/`:424-428`, `run_migrations_online` `:422`. All re-read this gate. | RESOLVED |
| **L-3** | Class-D reacher list not exhaustive | §6.4 adds `app/composition.py` reachers (six re-read; `:612` carried). | RESOLVED |
| **L-4** | Work-order citation drift — `backend/app/database/entity_repository/migration.py` does not exist | §5.12 states the real path `backend/app/entity_repository/migration.py` (TRACKED; the cited path is NOT TRACKED). The erroneous path is not reused as valid anywhere else. | RESOLVED |
| **L-5** | PRE-3 §0.3's "no root listing" is not independently checkable | §5.13, §18.2: this report makes only self-supported process claims and tags PRE-3's authoring-session claims UNVERIFIED. This gate executed no root listing and discloses no traversal deviation. | RESOLVED (framing) |
| **L-6** | §7.1(2) rule vs. §7.2's "correct use" contradiction regarding the two masked sites | §5.14, §8.3: the normative rule governs; **all four** URL-derived sites must change; §7.2's "correct use" endorsement is withdrawn. | RESOLVED |
| **L-7** | Cost figures hedged although exact | §7.1 uses exact figures (90/39, 21/12, 1/1, 3), re-measured and identical to the audit's. | RESOLVED |
| **L-8** | Row 8 disposes ACCEPT without stating the non-decoding consequence as a risk | §9.6 states the consequence fully and escalates the disposition choice to **D-4**. | RESOLVED as a disclosure; **D-4 OPEN** for the disposition |
| **L-DEV** | Disclosed process deviations (protected-path traversal; parse-probe preference) | §5.17: recorded as the audit recorded them, not repeated. This gate's own deviations are disclosed in §18.4 (a read-only third-party dialect-source probe; no traversal, no stat of the protected path). | RESOLVED (disclosure) |


**AUDIT-DRIVEN CORRECTION note.** Each L row above remains the reconciliation of the **original** audit's
L item (V1 audit, §7.4). Where the V1 audit additionally raised a LOW item against V1's handling of that
row, the V2 disposition is in §4.1 and §5.20–§5.25, and the mapping is in §19. No L-row status changes:
L-1…L-7 RESOLVED, L-8 RESOLVED as disclosure with **D-4 OPEN**, L-DEV RESOLVED as disclosure.

---

## 15. Complete traceability matrix

Columns: **AUDIT ID → original PRE-3 section → correction in this report → status → remaining dependency.**

**Identifier provenance — AUDIT-DRIVEN CORRECTION (V3), advisory NV-7.** `PC-01…PC-08` are findings of
the **V1 audit** (`PRE-3-CORRECTED-INDEPENDENT-AUDIT.md`), which labelled them "(new)" in its own vocabulary.
They are **not** findings of the correction passes that produced V1 or V2. **AUDIT-DRIVEN CORRECTION (V4)
— F-V8:** where the carried V2 text wrote “V1's PC-01” or “V1's PC-02”, those strings
are **historical references carried forward from V2**, retained only so this note can explain the
audit-driven correction; after V3's own edits they survive only inside the historical-quotation note at
§8.2 carriers #4/#5 (“V2 wrote …”). They are **not** the active inventory, which is
§8.2 carriers #4/#5. The intended referent is the V1 **audit**, not the V1 report.

| Audit ID | Original PRE-3 section | Correction here | Status | Remaining dependency |
|---|---|---|---|---|
| H-1 | §4.2 classes A/B/C, §8.3 PT-16, §9.2(7) | §5.1, §6.2–§6.6, §12 PT-16, §12.1 MT-01…MT-04 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | D-1 (allow-list membership of `migration.py`) |
| H-2 | §6.1(6), §6.4, §8.1, §14.2 D-3 | §5.2, §7.1–§7.5 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | D-3 (operator) |
| H-3 | §7.1, §7.2, §7.3 | §5.3, §5.18, §8.0–§8.8 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | none |
| M-1 | §5.2 row 9, §11.1, §8.3 PT-14 | §5.4, §9.3, §12 PT-14 | DESIGN ADDRESSED — expected values BLOCKED | D-2 (operator) |
| M-2 | §6.1(4),(5), §8.3 PT-15 | §5.5, §9.5, §12 PT-02/PT-15 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | D-3 changes the invariant form |
| M-3 | §5.3 P3-11, §8.3 PT-11 | §5.6, §9.4, §12 PT-11 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | none |
| M-4 | §9.2, §11.1 | §5.7, §10.3 | PARTIALLY ADDRESSED — BLOCKED | D-2 (operator) |
| M-5 | §10 opening vs §10.1/§10.2 | §5.8, §11 | DESIGN ADDRESSED — implementation BLOCKED | D-1 (operator) |
| L-1 | §1.1, §3, §8.3 | §5.9, §12 | RESOLVED | none |
| L-2 | §8.4, §10.1, §4.2 | §5.10, §8.1, §11 | RESOLVED | none |
| L-3 | §4.2 class D reachers | §5.11, §6.4 | RESOLVED | none |
| L-4 | §4.2 (correct) vs. audit WO (wrong path) | §5.12 | RESOLVED | none |
| L-5 | §0.3 | §5.13, §18.2 | RESOLVED (framing) | none |
| L-6 | §7.1(2), §7.2 | §5.14, §8.3 | RESOLVED | none |
| L-7 | §8.1 | §7.1 | RESOLVED | none |
| L-8 | §5.2 row 8 | §9.6 | RESOLVED disclosure | D-4 (operator) |
| L-DEV | §0.3 (PRE-3) / audit §0.2, §0.3 | §5.17, §18.4 | RESOLVED (disclosure) | none |
| AC-AUD-1 | PT-16 / class-C guard | §6, §12 PT-16, §12.1 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | D-1 |
| AC-AUD-2 | §6.1(4),(5), PT-15 | §9.5, §12 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | D-3 |
| AC-AUD-3 | §5.3 P3-11, PT-11 | §9.4, §12 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | none |
| AC-AUD-4 | §4.2 class D | §6.4 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | none |
| AC-AUD-5 | §6.4 | §7 | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | D-3 |
| AC-AUD-6 | §10 preamble, §5.1 step 5, §5.2 row 9 | §9.3, §11 | DESIGN ADDRESSED — expected values BLOCKED | D-2 |
| AC-AUD-7 | §7.1–§7.3 | §8.0–§8.8 (11 carriers, SL-1…SL-10, ST-01…ST-13) | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED | none |
| AC-AUD-8 | §9.2 | §10.3 | PARTIALLY ADDRESSED — BLOCKED | D-2 |
| AC-AUD-9 | §1.1, §3, §8.3, §8.4, §10.1, §4.2 | §5.9, §5.10, §9.6 | DESIGN ADDRESSED; `%20` disposition OPEN | D-4 |
| **PC-01** (V1-audit finding) | — | §8.2 **carrier #4** (`database.py:178`) — **AUDIT-DRIVEN CORRECTION (V3) / C-V2-2** (V2 cited "§8.1 site 4", stale: §8.1 is the scope statement) | NEW — SOURCE-CONFIRMED, exposure UNVERIFIED | none |
| **PC-02** (V1-audit finding) | — | §8.2 **carrier #5** (`database.py:183/:187` exception text) — **AUDIT-DRIVEN CORRECTION (V3) / C-V2-2** (V2 cited "§8.1 site 5") | NEW — SOURCE-CONFIRMED | none |
| **PC-03** (V1-audit finding) | §5.2 row 3 | §9.2, §9.4 V3 | NEW — SOURCE-CONFIRMED (contradicts PRE-3 label) | none |
| **PC-04** (V1-audit finding) | §5.2 rows 6, 6b | §9.2, §9.4 V6, V7 | NEW — SOURCE-CONFIRMED (contradicts PRE-3 and the audit's comment) | none |
| **PC-05** (V1-audit finding) | §5.3 P3-11 | §9.4 parity clause — **mismatch set corrected to `{V3, V5, V6}`; V7 excluded (MED-2)** | NEW — SOURCE-CONFIRMED, **corrected this pass** | none |
| **PC-06** (V1-audit finding) | — | §5.1 (AC-AUD-1's list is itself unsatisfiable) | NEW — SOURCE-CONFIRMED | none |
| **PC-07** (V1-audit finding) | §9.1 | §7.1, §10.1 (no `conftest.py`; `pytest.ini` has no `pythonpath`; one step has `PYTHONPATH`) | NEW — SOURCE-CONFIRMED | none |
| **PC-08** (V1-audit finding) | §8.3 (PT-20) | §12 PT-20 (`app/config/database.py` holds three `sqlite://` literals) | NEW — SOURCE-CONFIRMED | none |
| **K-1…K-8** | §14.1 | carried unchanged; K-2/K-3/K-7 now depend on D-3/D-1 respectively | CARRIED | D-1, D-3 |
| **D-1** | §10, §14.2 | §4.3, §11 | OPEN / BLOCKED | operator |
| **D-2** | §11.1, §14.2 | §4.3, §9.3, §10.3 | OPEN / BLOCKED | operator |
| **D-3** | §6.4, §14.2 | §4.3, §7 | OPEN | operator |
| **D-4** (new) | §5.2 row 8 | §4.3, §9.6 | OPEN | operator |
### 15.1 Rows added by this pass (audit findings, and findings of this pass)

| Audit ID | Requirement / meaning (preserved) | Resolved in V2 | Status | Remaining dependency |
|---|---|---|---|---|
| **MED-1** (WO C-1) | Extend §8.1's disclosure inventory to the in-memory-config and exception-text carriers and cite `pysqlite.py:566-573`; add an ST test for the migration exception path. | §4.1, §5.3, §5.18, §8.0–§8.8 (carriers #7, #8, #9; ST-09/ST-10) | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | none |
| **MED-2** (WO C-2) | Correct the `session.py:167` mismatch set to `{V3, V5, V6}`; reassess derived rows; keep V7's library-internal point separately. | §4.1, §5.19, §9.4, §12 PT-11, §15 (PC-05) | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | none |
| **MED-3** (WO C-3) | Restate L3/PT-16 on the real execution boundary; separate template / live path / third-party; add mutation tests for boundary bypass and alternate ungated paths. | §4.1, §5.19-equivalent (§6.2, §6.5), §12 PT-16, §12.1 (MT-04 reinterpreted, MT-05…MT-07) | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** | D-1 (Branch selection) |
| **LOW-1** | V5 driver-filename key ordering. | §5.20, §9.4 row V5 | **CORRECTED — QUALIFIED** | none |
| **LOW-2** | PC-08 three-literal wording. | §5.21, §12 PT-20 | **CORRECTED — SOURCE CONFIRMED** | none |
| **LOW-3** | Additional dormant caller `migration.py:529`. | §5.22, §6.2, §4.1 | **CORRECTED — SOURCE CONFIRMED** | none |
| **LOW-4** | Compliant redacted `__repr__` sites. | §5.23, §8.3 (Inventory B) | **CORRECTED — SOURCE CONFIRMED** | none |
| **LOW-5** | `create_engine` import at `session.py:18`. | §5.24, §6.5, §8.2, §12 PT-16 | **CORRECTED — SOURCE CONFIRMED** | none |
| **LOW-6** | Material markdown typography. | §5.25 — **corrected in V3 (C-V2-1)**: the byte-confirmed defect is V1's **footer** (split statement + lone trailing `*`); V1's and V2's front matter is **already balanced** and was **never changed**; V2's three-asterisk quotation is withdrawn; V3's own footer is §20.7. | **CORRECTED — QUALIFIED** | none |
| **LOW-UNVERIFIED** | Output-path pre-existence is an authoring-session process claim. | §5.25, §17.2 | **CORRECTED — QUALIFIED** | none (not independently checkable) |
| **PW-01** (this pass) | The exception-text carrier class is **wider** than the audit's two lines: `migration.py:178/:193/:237/:252/:267/:286/:317`/`:318`, `database.py:137`/`:229`, `session.py:266-275` (`:272`). | §8.2 carriers #9, #10, #11; §5.18 | **NEW — SOURCE-CONFIRMED** (exposure for the non-URL-bearing messages remains UNVERIFIED) | none |
| **PW-02** (this pass) | SQLAlchemy 2.0.51's URL-parse failure does **not** echo the input (`url.py:920-924`) — a **negative** finding that V2 must not overclaim. | §8.4 | **NEW — SOURCE-CONFIRMED** | none |
| **PW-03** (this pass) | The work order's LOW-2 path `backend/config/database.py:17` is itself drifted — the path is **not tracked**; the real path is `backend/app/config/database.py`. | §5.21 | **NEW — SOURCE-CONFIRMED** | none |
| **PW-04** (this pass) | "Empty index" is ambiguous: the **staging area** is empty (0 staged) while the **index tracks 793** files. | §3.1, §18 | **NEW — SOURCE-CONFIRMED** | none |
| **PW-05** (this pass) | `migration.py:103-106` (in-memory config) is a **distinct carrier class** from `migration.py:348/:384` (persistent write); treating them as equivalent would be wrong. | §8.2 (#7 vs #6), §8.5 (SL-10) | **NEW — SOURCE-CONFIRMED** | none |
| **D-1** | Alembic Branch A vs Branch B. | §4.4, §11 | **OPEN / BLOCKED** | operator |
| **D-2** | Target OS / `PLATFORM_PROFILE`. | §4.4, §9.3, §10.3 | **OPEN / BLOCKED** | operator |
| **D-3** | Mode provenance O1/O2/O4. | §4.4, §7 | **OPEN** | operator |
| **D-4** | Percent-encoded disposition. | §4.4, §9.6 | **OPEN** | operator |


---

## 16. Remaining blockers, residual risks and explicit implementation gates

### 16.1 Blockers (nothing can be implemented until these are answered)

1. **D-1** — Alembic Branch A vs. Branch B (§11). Blocks: allow-list membership of
   `app/database/migration.py`, PT-16's permitted counts, and whether schema-ownership work must precede the
   gate.
2. **D-2** — target host OS / `PLATFORM_PROFILE` (§9.3, §10.3). Blocks: the platform predicate's expected
   values, PT-14, the CI runner pin (AC-AUD-8 is otherwise PARTIALLY ADDRESSED).
3. **D-3** — mode provenance option O1/O2/O4 (§7). Blocks: the structural guard's invariant form (PT-15) and
   the test-migration plan.

### 16.2 Open but non-blocking

4. **D-4** — percent-encoded disposition (§9.6). Changes PT-12's expected value only.

### 16.3 Residual risks (stated, not mitigated)

- **Dynamic construction escape.** A text/AST guard cannot detect fully dynamic engine construction
  (`getattr`, `importlib`, `eval`, plugin-loaded code) — §6.6. The boundary refusal (not the guard) is the
  load-bearing control.
- **Declared-profile vs. host mismatch.** Even with `PLATFORM_PROFILE`, the SQLAlchemy dialect abspaths with
  the **host's** `os.path`; the design therefore requires a fail-closed profile/host consistency check
  (§9.3(3)), which is a *design* requirement, **not an implemented control**.
- **CWD dependence remains.** Without `uri=true`, the dialect silently `abspath`s a relative SQLite
  database against the process CWD — confirmed in dialect source. Preventing a *relative* URL in production
  is therefore not cosmetic; it is the only thing standing between a relative URL and a CWD-dependent file.
- **Dormant cleartext `alembic.ini` write** (`migration.py:348`/`:384`) remains a credential-at-rest hazard
  until Branch B is addressed or the path is removed.
- **Runtime and deployment facts remain UNVERIFIED.** No connection was opened; effective SQLite driver
  defaults, busy timeout, real concurrency, and whether the operator's relative default fails on first
  connect are unestablished. No deployment artifact exists.

### 16.4 Implementation gates (for the future, separately authorised work order)

- G1 — D-1, D-2, D-3 answered (D-4 recommended).
- G2 — the scoped invariant (§6.3) adopted verbatim, including the corrected three allow-lists.
- G3 — the secret rule (§8.3) adopted with ST-01…ST-08.
- G4 — the oracle (§9.4) adopted, with `session.py:167` corrected in the same change.
- G5 — the CI design (§10) adopted as an **acceptance criterion**, including the collected-node-ID equality
  assertion and a passing mutation step (MT-01…MT-04).
- G6 — the branch disclosure (Branch A or Branch B) stated in the implementation report.
- G7 — the protected-object discipline preserved (`?? 500` reported only; never staged, restored, opened,
  hashed or stat-ed; no `git add -A` / `clean` / `reset` / `stash` / `restore` / `checkout`).

### 16.5 Status of the audit's three conditions and the advisory items in this pass (AUDIT-DRIVEN CORRECTION)

**C-1 (MED-1): DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.** §8 rebuilt (§8.0–§8.8); the two named sites
and the wider exception-text class are inventoried with per-site dispositions; the mechanism is cited and
bounded; ST-09…ST-13 added. No code change is claimed.
**C-2 (MED-2): DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.** The mismatch set is `{V3, V5, V6}`
everywhere it occurred; V7's library-internal point is retained separately.
**C-3 (MED-3): DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED.** L3/PT-16 now rests on the real execution
boundary (`run_migrations` `:486`, `ensure_database_schema` `:506`, `command.upgrade` `:158`), with the
template/live/third-party distinction stated and MT-04…MT-07 defined.
**LOW-1…LOW-6, LOW-UNVERIFIED: dispositioned** per §4.1 — **four `SOURCE CONFIRMED` (LOW-2, LOW-3, LOW-4, LOW-5), three `QUALIFIED` (LOW-1, LOW-6, LOW-UNVERIFIED)**. **AUDIT-DRIVEN CORRECTION (V3) / C-V2-1:** moving LOW-6 from `SOURCE CONFIRMED` to `QUALIFIED` (§5.25) is what makes this count correct; V2's sentence already read "four … three" while V2's own §4.1 table showed **five** `SOURCE CONFIRMED`, so V2's count contradicted its own table.

### 16.6 Additional implementation gates introduced by this pass

- **G8** — the corrected L3 predicate (§6.5) adopted **verbatim**: `engine_from_config` may appear **only**
  inside the `env_py_content` template, and the runtime-path assertion that `command.upgrade` is unreached
  when the validator refuses must be part of the acceptance criteria, not optional.
- **G9** — ST-09…ST-13 (§8.8) adopted, including the **fail-open negative test** (the canonical redactor
  must never return its input unchanged on a secret-bearing pattern) and the in-memory-config assertion.
- **G10** — the match on **call syntax** (not bare names) is part of PT-16's L1/L2 predicates, and **AUDIT-DRIVEN CORRECTION (V3) / C-V2-3** states them over **both** the `ast.Name` and the `ast.Attribute` call form (`create_engine(…)`, `sqlalchemy.create_engine(…)`, `connect(…)`, `sqlite3.connect(…)`), with bounded positive/negative examples (§6.5, §6.6), **closing BYPASS-1 at the specification level only** — **AUDIT-DRIVEN CORRECTION (V4) — F-V7:** this is a **documentation** closure; it is **not** proof of an implemented or tested runtime guard, and no guard was written, executed or tested — so the
  module-level import binding at `session.py:18` cannot be mistaken for a construction (LOW-5).


---

> **V3 note (AUDIT-DRIVEN CORRECTION).** §17 below is **V2's own** integrity record, carried forward
> unchanged. Its byte count (`156249`) and its series-convention digest identify **V2's bytes** — i.e. the input
> to this pass — **not** V3's bytes. V3's own identity and read-back record is §20.5, and V3 does **not** embed
> its own stored-file digest, because a file cannot contain the digest of itself.

## 17. Final integrity record

### 17.1 Digest convention (same series convention as PRE-1 / PRE-2 / PRE-3 / both audits)

The series-convention SHA-256 below is computed over this file **with the designated 64-hex digest field
replaced by 64 zero characters** (the **exact** zeroing rule: take the hex token on the single line that
follows the label `- **SHA-256 (series convention — 64-hex digest field zeroed):**`, replace all 64
characters with `0`, and hash the resulting file). It is **not** the SHA-256 of the bytes on disk. The token
was asserted to occur **exactly once** in the file before hashing.

*Self-reference note:* a file cannot contain its own stored digest. Because the digest field is exactly 64
characters, the substitution preserves file length, so the byte count below is true of the delivered file
while the digest below is independently reproducible under the stated rule. The **true stored-file
SHA-256** is reported in the final response to the work order, **not** here.

### 17.2 Report identity

- Path: `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V2.md`
- Location: **outside** the repository (`/opt/data/output/`) — verified.
- **Pre-existing artifact at this path:** the **initial operation** of this gate was a listing of the
  output directory (`os.listdir('/opt/data/output')`, **outside** the repository); this file was **not**
  present in it, so the write created the file and **nothing was overwritten or displaced**. This claim is
  supported by an operation **this** gate performed — unlike V1 §17.2's claim about V1's own authoring
  session, which remains independently unverifiable (LOW-UNVERIFIED). *Scope note:* this is a statement about **this** gate's own write target and was verifiable by
  this gate because it was made by this gate. V1 §17.2's equivalent statement about **V1's** authoring
  session remains an **author-reported process fact that no later reader can independently verify** —
  recorded as such, per LOW-UNVERIFIED (§5.25); no attempt was made to reconstruct missing historical
  filesystem state.
- **Byte count (stored file):** `156249` bytes
- **SHA-256 (series convention — the designated 64-hex field zeroed):**
  `a96ee5c47470a6af3b8d9df10b49720082dbf063ca73536db2e260e23ed63a19`
- Inputs neither overwritten nor modified: V1, the V1 audit, PRE-1, PRE-2, the current PRE-3 and the
  previous audit are preserved at their verified identities (§2.1, §2.2).

### 17.3 Read-back verification

After writing, the file was re-read **from disk**; its byte count and stored-file SHA-256 were recomputed,
and the series-convention digest was re-derived by applying the zeroing rule above — which reproduced the
value printed in the field. The audit of V2 must pin the **stored-file SHA-256** reported in the work-order
final response.

---



---

## 18. Final repository-state comparison and deviations (this gate)

### 18.1 Final state (re-captured after the report was written)

```
$ git rev-parse --abbrev-ref HEAD            -> main
$ git rev-parse HEAD                         -> 1f20e9a867ce7d286e6e72a71ddefeec8f7f9264
$ git rev-parse refs/heads/main              -> 1f20e9a867ce7d286e6e72a71ddefeec8f7f9264
$ git rev-parse refs/remotes/origin/main     -> 1f20e9a867ce7d286e6e72a71ddefeec8f7f9264
$ git rev-list --left-right --count main...origin/main -> 0   0
$ git diff --cached --name-only | wc -l      -> 0        (zero staged changes)
$ git stash list                             -> (empty — zero stashes)
$ git status --porcelain=v1                  -> 7 entries, IDENTICAL to §3 (same order)
```

**Comparison method:** initial and final porcelain captures compared as **ordered line lists** — never with
a global `.strip()`, which would consume the leading space of the first entry (`" M …"`) and manufacture a
false difference. Result: **IDENTICAL**.

**No repository file was created, modified, deleted, renamed, moved, staged or restored.** The staging area
is empty; the index still tracks **793** files; stash empty; `refs/heads/main` and
`refs/remotes/origin/main` unmoved. The protected path appears **only** as the porcelain text `?? 500`; it
is **not ignored** and **not tracked**; per standing rule it is **reported, never restored**.

### 18.2 Operations actually performed (all read-only)

`git rev-parse` (branch / HEAD / refs), `git rev-list --left-right --count`, `git status --porcelain=v1`
(initial and final), `git diff --cached --name-only`, `git diff --cached --stat`, `git stash list`,
`git remote -v`, `git diff --name-only`, `git ls-files --error-unmatch` and `git ls-files` **on explicit
paths/patterns only**, `git grep -n/-o/-l` **bounded to explicit subtrees** (`backend`, `backend/app`,
`backend/main.py`, `backend/tests`), `grep` over **explicit third-party source paths**, read-only
`read_file` of **explicit known source paths**, and `os.path.getsize` + `hashlib.sha256` over the six
report files (all outside the repository). A single `os.listdir('/opt/data/output')` — **outside** the
repository — was this gate's first operation and is the basis of the §17.2 pre-existence statement; it
enumerates only that output directory and never the repository.

**Operations NOT performed:** no test execution; no application-module import; no application process or
service started; no migration; no database creation/opening/connection; no engine construction; no package
installation; no environment-variable modification; **no `ls` of the repository root; no `find`; no
`os.walk`; no recursive directory traversal; no broad glob**; no `stat`/size/inode/mtime of the protected
path; no secret or credential-bearing value read, printed or disclosed; no `fetch`, `pull`, `ls-remote`,
`push`, `branch`, `tag`, `PR`, `merge`, `rebase`, `reset`, `clean`, `stash`, `git add`, `checkout` or
`switch`. **The remote was never contacted.**

### 18.3 Premises re-verified for this report's own claims

- **`engine_from_config` has exactly two textual occurrences** in `backend/app` + `backend/main.py`
  (`migration.py:393`, `:424`), **both inside** the `env_py_content` template (`:389-444`); **zero** live
  call nodes. Used in §6.2, §6.5, §12. `[SOURCE-CONFIRMED]`
- **`create_engine`**: one import (`session.py:18`) + three call sites (`:168`, `:175`, `:188`) + four
  docstrings. Used in §6.5, §8.2, §12. `[SOURCE-CONFIRMED]`
- **`sqlite3.connect`**: exactly one (`entity_repository/migration.py:9`); `apply_migrations` is
  **UNREFERENCED**. Used in §6.2. `[SOURCE-CONFIRMED]`
- **`set_main_option("sqlalchemy.url", self.database_url)`** at `migration.py:103-106`; exception loggers at
  `:144` and `:161`; persistent write at `:384`. Used in §5.18, §8.2. `[SOURCE-CONFIRMED]`
- **`pysqlite.py:566-573`** formats the URL into `ArgumentError`; **`url.py:630-667`** masks only the
  userinfo password; **`url.py:920-924`** does **not** echo the input on parse failure. Used in §8.4.
  `[SOURCE-CONFIRMED]`
- **`pysqlite.py:609-615`** sorts the URI query keys for the driver filename. Used in §9.4, §5.20.
  `[SOURCE-CONFIRMED]`
- **Six boundary call sites** (five live + `migration.py:529` dormant). Used in §6.2, §5.22.
  `[SOURCE-CONFIRMED]`
- **Exactly one workflow** (`.github/workflows/severity-governance.yml`), **no `conftest.py`**, **no
  `alembic.ini`**, `backend/migrations/` holds only `__init__.py`. Used in §5.22, §10.1, §11.
  `[SOURCE-CONFIRMED]`
- **`backend/app/config/database.py`** holds three `sqlite:///` literals (`:17` relative default; `:34`,
  `:42` prefix comparisons); `backend/config/database.py` is **NOT tracked**. Used in §5.21.
  `[SOURCE-CONFIRMED]`

### 18.4 Deviations disclosed by this gate

- **DV-1 (method — read-only content search over tracked files).** `git grep`, bounded to explicit
  subtrees, was used to measure counts (90/39, 21/12, 1/1, 3, the call-site enumerations, the
  `ENVIRONMENT`/`APP_ENV` checks). `git grep` reads **tracked** content only and therefore **cannot
  enumerate or read** the untracked protected entry; it performed no filesystem traversal of the working
  tree and no directory enumeration. Judgement: the work order requires these counts to be
  **re-verified from safe, explicit source references**, and `git grep` over tracked paths is exactly that.
- **DV-2 (method — index listing).** `git ls-files --stage | wc -l` (= 793) was used once to make the §3.1
  precision point. It lists **index entries** (tracked files) and does not enumerate untracked paths, so the
  protected entry cannot appear in it.
- **DV-3 (index stat-cache).** `git status --porcelain=v1` was run initially and finally (read-only); Git
  may refresh its own index stat-cache inside `.git/`. Porcelain output was **identical** in both captures
  and no tracked file changed.
- **DV-4 (no probe).** Unlike V1 (which disclosed a third-party interpreter probe) and the previous audit
  (which disclosed DV-A/DV-B), **this gate executed no Python interpreter invocation of its own and imported
  no Python module** — every third-party claim in §8.4/§9.4/§5.20 was established by **reading source text
  at explicit paths**, and every count by `git grep`. `sqlalchemy` was **not** imported, no URL was parsed
  at runtime, no engine was created and no connection was opened. Therefore **no evidence file and no
  helper file was authored by this gate** anywhere, including `/tmp`.
- **DV-5 (tooling artifact — disclosed for completeness).** The code-execution sandbox that produced this
  report materialises its own **ephemeral** script under
  `/tmp/hermes_sandbox_<random>/script.py` and removes it with the sandbox. It is a **tooling** artifact,
  not authored content, it is **outside** the repository, and it contains no credential and no repository
  write. Disclosed rather than omitted.
- **DV-6 (none).** **No `ls` of the repository root, no `find`, no `os.walk`, no recursive traversal, no
  broad glob, and no stat/size/inode/mtime of the protected path `500`** were performed. The protected path
  was observed **only** as its literal porcelain line. This gate therefore has **no traversal deviation to
  disclose**.

### 18.5 Statement of non-mutation

**No repository file, test, CI workflow, configuration, migration, database or remote state was changed by
this gate.** No repository file was created, modified, staged, deleted, renamed, moved or restored. **No
implementation, test, CI, database, migration, Git or production change was authorised or performed.** The
only filesystem write was this single external report at
`/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V2.md`. V1, the V1 audit, PRE-1, PRE-2, the
current PRE-3 and the previous audit were **read only**, at their verified identities.

---



---

## 19. Correction matrix — every audit finding and condition mapped (this pass)

### 19.1 Work-order §9 required verification matrix (verbatim rows)

| Finding | Required disposition | Where satisfied in V2 | Status achieved |
|---|---|---|---|
| **MED-1 / C-1** | Secret-disclosure inventory extended; exception-text mechanism addressed | §4.1, §5.3, §5.18, §8.0–§8.8 (carriers #7, #8, #9, #10, #11; §8.4 mechanism + negative finding; §8.5 SL-8…SL-10; §8.8 ST-09…ST-13) | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** |
| **MED-2 / C-2** | PC-05 mismatch set independently corrected | §4.1, §5.19, §9.4, §12 PT-11, §15 (PC-05) — set = **`{V3, V5, V6}`** | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** |
| **MED-3 / C-3** | L3/PT-16 redesigned around the real execution boundary | §4.1, §6.2, §6.5, §12 PT-16, §12.1 (MT-04 reinterpreted; MT-05…MT-07) | **DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED** |
| **LOW-1** | V5 ordering corrected or qualified | §5.20, §9.4 row V5 | **CORRECTED — QUALIFIED** |
| **LOW-2** | Three-literal wording corrected | §5.21, §12 PT-20 | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-3** | Additional caller reconciled | §5.22, §6.2, §15 | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-4** | Redacted `__repr__` controls inventoried | §5.23, §8.3 | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-5** | Import/call distinction corrected | §5.24, §6.5, §8.2, §12 PT-16 | **CORRECTED — SOURCE CONFIRMED** |
| **LOW-6** | Material typography ambiguity corrected | §5.25 — **V3 / C-V2-1**: byte-confirmed **footer** defect corrected; front matter unchanged (already balanced); V2's three-asterisk quotation withdrawn; V3 footer §20.7 | **CORRECTED — QUALIFIED** |
| **LOW-UNVERIFIED** | Historical process claim accurately qualified | §5.25, §17.2 | **CORRECTED — QUALIFIED** |
| **D-1** | OPEN | §4.4, §11, §16.1 | **OPEN / BLOCKED** |
| **D-2** | OPEN | §4.4, §9.3, §10.3, §16.1 | **OPEN / BLOCKED** |
| **D-3** | OPEN | §4.4, §7, §16.1 | **OPEN** |
| **D-4** | OPEN | §4.4, §9.6, §16.2 | **OPEN** |

### 19.2 Preserved reconciliation (unchanged, re-indexed)

| Family | Where preserved in V2 | Status |
|---|---|---|
| **H-1, H-2, H-3** | §5.1, §5.2, §5.3 (+ §5.18, §8.0–§8.8 for H-3's expansion) | DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED (H-3's added sub-conditions likewise) |
| **M-1…M-5** | §5.4–§5.8 | as in V1 (M-4 PARTIALLY ADDRESSED, BLOCKED on D-2; M-5 BLOCKED on D-1) |
| **PC-01…PC-08** (findings of the **V1 audit**, not of the correction passes — **AUDIT-DRIVEN CORRECTION (V3), NV-7**) | §5.3 (PC-01, PC-02), §5.6/§9.4 (PC-03, PC-04, PC-05 — **PC-05 corrected**), §5.1 (PC-06), §7.1/§10.1 (PC-07), §12 PT-20 (PC-08) | NEW — SOURCE-CONFIRMED; PC-05's set corrected this pass |
| **AC-AUD-1…AC-AUD-9** | §13 | unchanged statuses; AC-AUD-7 span widened by §8, AC-AUD-1's L3 component by §6.2/§6.5 |
| **L-1…L-8, L-DEV** | §14 | unchanged: L-1…L-7 RESOLVED; L-8 RESOLVED as disclosure with D-4 OPEN; L-DEV RESOLVED as disclosure |
| **PW-01…PW-05** (this pass) | §3.1, §5.18, §5.21, §8.2, §8.4, §18 | NEW — SOURCE-CONFIRMED |

### 19.3 Correction trace (what changed, where, on whose authority)

| # | V1 statement (superseded) | Superseding V2 statement | Section | Authority |
|---|---|---|---|---|
| 1 | "§8 reconciles the **complete** disclosure surface" (six paths) | Scoped completeness claim; **11 carriers in four classes** | §8.0–§8.2 | **AUDIT-DRIVEN CORRECTION** — MED-1 / C-1 |
| 2 | "`session.py:167` disagrees with the oracle on **V3, V5, V6 and V7**"; "says MEMORY for V6 and V7" | Mismatch set = **`{V3, V5, V6}`**; V7 agrees (FILE/FILE) | §5.19, §9.4 | **AUDIT-DRIVEN CORRECTION** — MED-2 / C-2 |
| 3 | L3 allow-list target = "`migration.py:424`", "exactly one `engine_from_config`" | L3 = **template content**, zero live call nodes; invariant at `run_migrations` `:486` / `ensure_database_schema` `:506`; runtime-path test load-bearing | §6.2, §6.5, §12 PT-16 | **AUDIT-DRIVEN CORRECTION** — MED-3 / C-3 |
| 4 | V5 row states the class only | V5 row also states the **sorted** driver filename `file:memdb?cache=shared&mode=memory` | §9.4 | **AUDIT-DRIVEN CORRECTION** — LOW-1 (qualified) |
| 5 | "three `sqlite://` literals (relative defaults)" | **One** relative default (`:17`) + **two** prefix comparisons (`:34`, `:42`) | §12 PT-20, §5.21 | **AUDIT-DRIVEN CORRECTION** — LOW-2 |
| 6 | "four live entrypoint paths" | **Six** boundary call sites — five live + `migration.py:529` dormant | §6.2, §5.22 | **AUDIT-DRIVEN CORRECTION** — LOW-3 |
| 7 | Inventory omitted the two compliant `__repr__` sites | Inventory B records them as **compliant controls** | §8.3 | **AUDIT-DRIVEN CORRECTION** — LOW-4 |
| 8 | "every other `create_engine` hit is a docstring … or a test" | **Import at `session.py:18`** added; import ≠ construction | §6.5, §8.2, §12 PT-16 | **AUDIT-DRIVEN CORRECTION** — LOW-5 |
| 9 | V2's row 9 claim: a three-asterisk front-matter defect plus a split footer sentence | **AUDIT-DRIVEN CORRECTION (V3) / C-V2-1:** the three-asterisk front-matter claim is **withdrawn** — V1's lines 13—15 are already balanced and V2's lines 15—17 are **byte-identical** to them, so **no front-matter change was made or needed**. The real defect is the **footer** (split NOT-GRANTED statement + lone trailing `*`), corrected in V3's own footer. | §5.25, §20.7 | **AUDIT-DRIVEN CORRECTION (V3)** — C-V2-1 (supersedes V2's LOW-6 claim) |
| 10 | V1 §17.2 asserted no pre-existing artifact "before the write" | Recorded as an **author-reported, independently unverifiable** process fact | §17.2 | **AUDIT-DRIVEN CORRECTION** — LOW-UNVERIFIED |
| 11 | "empty index" | Staging area empty; **index tracks 793** entries | §3.1, §18 | this pass — PW-04 |
| 12 | (absent) | Exception-text carrier **class** enumerated across three modules | §8.2 | this pass — PW-01 |
| 13 | (absent) | SQLAlchemy 2.0.51 does **not** echo the URL on parse failure (negative finding) | §8.4 | this pass — PW-02 |
| 14 | (absent) | `backend/config/database.py` is **not tracked**; real path `backend/app/config/database.py` | §5.21 | this pass — PW-03 |
| 15 | (absent) | In-memory Alembic config ≠ persistent config write | §8.2 (#7 vs #6), §8.5 | this pass — PW-05 |

**No V1 statement outside this trace was altered.** V1 sections not listed in §19.3 are carried forward
verbatim (§0 of this report lists them).

---


## Part III — V3 corrections, change log and integrity record

### 20.1 Correction matrix — every audit finding this pass addresses

Statuses use the permitted vocabulary `CORRECTED — SOURCE CONFIRMED`, `CORRECTED — QUALIFIED` and
`OPEN — EVIDENCE INSUFFICIENT`. **No item is marked resolved on wording alone**, and **no item is marked
`SOURCE CONFIRMED` on source this work order did not authorise this gate to read.**

| Finding | Required disposition | V3 section that resolves it | Basis of verification in this pass | Status |
|---|---|---|---|---|
| **C-V2-1** (LOW-6 / footer) | Re-read the actual V1 bytes; withdraw the unsupported byte-exact quotation; do not claim V2's front matter was corrected; make V3's footer internally consistent | §5.25 (rewritten), §4.1, §15 (LOW-6 row), §19.1, §19.3 row 9, §20.7 | **Hex dumps + exact list comparison** of the V1 and V2 bytes, performed in this pass | **CORRECTED — QUALIFIED** |
| **C-V2-2** (PC-01/PC-02 provenance) | Re-point §15's PC-01/PC-02 rows from "§8.1 site 4/5" to §8.2 carriers #4/#5; verify against the report's own inventory | §15 (rows PC-01, PC-02) | Verified against **V2's own headings and inventory numbering** (§8.1 is the scope statement; the carriers live in §8.2) | **CORRECTED — SOURCE CONFIRMED** |
| **C-V2-3** (BYPASS-1 / AST coverage) | Define the L1/L2 predicates over both `ast.Name` and `ast.Attribute` call forms with bounded positive/negative examples, or state the limitation plainly | §6.5 (three predicate rows), §6.6 (limits), §12 PT-16, §16.6 G10 | **Option 1 chosen.** Predicates specified over both forms, **documentation only** — no code written and nothing tested | **CORRECTED — SOURCE CONFIRMED** |
| **NV-2** | Requalify the `operator/entrypoint.py:53-60` example | §8.3 (row 3 requalified; "never its value" withdrawn) | **`AUDIT-CONFIRMED`** — the audit's own source citation; **the source was not re-read here** (work-order read restriction, §20.6 DV-3) | **CORRECTED — QUALIFIED** |
| **NV-4** | Name vector V3 in the pooling-consequence discussion | §9.4 (pooling paragraph now names vectors V3, V5 and V6) | Verified against **V2's own §9.4**: its corrected set already contains V3 while the sentence named only V5 and V6 | **CORRECTED — SOURCE CONFIRMED** |
| **NV-5** | Do not present AC-AUD-1's condensation as a quotation | §5.1 (quotation withdrawn; paraphrase used) | **`AUDIT-CONFIRMED`** — `PRE-3-INDEPENDENT-AUDIT.md` is outside this work order's authorised reading | **CORRECTED — QUALIFIED** |
| **NV-6** | Qualify the query-parameter claim (values are `quote_plus`-encoded, not raw) | §8.4 (mask bound, and the query-parameter bullet) | Verified against **V2's own §8.4**, which already records `quote_plus` while calling the exposure "verbatim" — an internal inconsistency in V2's own bytes | **CORRECTED — SOURCE CONFIRMED** |
| **NV-7** | Correct PC identifier provenance attribution | §15 (provenance note + PC row labels), §8.2 carriers #4/#5, §19.2 | Verified against **V2's own bytes** (the "(new)" labels and the "V1's PC-01/02" renderings) | **CORRECTED — SOURCE CONFIRMED** |

**Status reductions disclosed.** Where V2 awarded `CORRECTED — SOURCE CONFIRMED` to LOW-6 on evidence its own
bytes do not support, V3 **reduces** that status to `CORRECTED — QUALIFIED` (§5.25, §4.1, §15, §19.1)
and says so. Where the required confirmation would depend on a document this work order does not authorise
reading, V3 records `CORRECTED — QUALIFIED` and names the limitation (NV-2, NV-5) rather than asserting
`SOURCE CONFIRMED`.

### 20.2 Change log — source-byte facts distinguished from interpretation

| # | Item | Class | Evidence |
|---|---|---|---|
| 1 | V1 lines 13—15 are `**…:** NOT GRANTED` — 4 asterisks each, balanced | **SOURCE-BYTE FACT** | hex + `str.count` on V1 |
| 2 | V2 lines 15—17 are byte-identical to V1 lines 13—15 | **SOURCE-BYTE FACT** | list equality (`==`) returns `True` |
| 3 | V1 line 1277 carries 8 asterisks and **ends** `authorization:` | **SOURCE-BYTE FACT** | hex tail `…617574686f72697a6174696f6e3a` |
| 4 | V1 line 1278 is `NOT GRANTED.*` (one lone trailing asterisk) | **SOURCE-BYTE FACT** | hex `4e4f54204752414e5445442e2a` |
| 5 | V2 lines 1933/1934 split the NOT-GRANTED statements and carry a trailing asterisk | **SOURCE-BYTE FACT** | hex of both lines |
| 6 | "V2's front matter was corrected" is **false** | **SOURCE-BYTE FACT** (a byte claim, negated) | list equality (item 2) |
| 7 | Byte facts over V1 lines 1273–1278: the NOT-GRANTED statement is **split across lines 1277/1278**; line 1278 ends with **one lone `*`**; the block's asterisk inventory is **1 + 8 + 1 = 10** — five balanced pairs — in one non-blank-separated paragraph | **SOURCE-BYTE FACT** | hex + `str.count` on V1 lines 1273–1278, this pass |
| 7a | Reading that lone `*` as an **“unterminated emphasis span at end of file”** | **INTERPRETATION** — **not byte-obtainable, and WITHDRAWN**: the measured inventory shows the italic span opened at V1 line 1273 closes at V1 line 1278, so the file's emphasis is balanced | markdown emphasis semantics |
| 8 | V2's stored bytes **do** contain a three-asterisk run — V2 line 670 and V2 line 674 each carry `2a2a2a` (`***`) inside V2's own quotation of V1's front matter — while **V1's** bytes do **not** (V1 lines 13–15 carry `2a2a` + text + `2a2a`, i.e. four asterisks, balanced). V2's “byte-exact” claim was therefore a **transcription error in V2**, not a console artifact and not “not file content”. (Console rendering in this series' tooling *also* distorts asterisk runs — a separate, real artifact of the tooling, kept distinct from file bytes.) | **SOURCE-BYTE FACT** | hex dumps of V1 lines 13–15 and V2 lines 670, 674 |
| 9 | §8.1 is V2's scope statement and the carriers are §8.2 #1…#11, so "site 4/5" is stale | **SOURCE-BYTE FACT** (against the report's own headings) | V2 §8.1…§8.2 |
| 10 | V2's L1 predicate matched only `Call(func=Name(…))` and L2 only the `Attribute` form | **SOURCE-BYTE FACT** (against V2's own text) | V2 §6.5, §6.6 |
| 11 | Vector V3 (`sqlite://`) is mis-selected and omitted from V2's pooling sentence | **SOURCE-BYTE FACT** (against V2's own §9.4) | V2 §9.4 set + sentence |
| 12 | V2 states query values are `quote_plus`-encoded yet calls the exposure "verbatim" | **SOURCE-BYTE FACT** (internal inconsistency) | V2 §8.2 / §8.4 |
| 13 | `PC-01…PC-08` originate in the **V1 audit** | **AUDIT-CONFIRMED** | V2 audit §9.1; V2's own "(new)" labels |
| 14 | `operator/entrypoint.py` interpolates the host value (`% host`) | **AUDIT-CONFIRMED** — **not re-read here** | V2 audit §10.1 (NV-2) |
| 15 | AC-AUD-1's exact source wording | **AUDIT-CONFIRMED** — **not re-read here** | V2 audit §10.1 (NV-5) |
| 16 | The V1 and V2 input identities reproduce from disk | **SOURCE-BYTE FACT** | fresh full-file SHA-256, this pass |

Every correction that rests on a byte comparison is proved from hex or list equality. The two items that rest
on a document outside this work order's authorised reading (14, 15) are labelled `AUDIT-CONFIRMED`, are marked
`QUALIFIED` in §20.1, and are **not** presented as `SOURCE-CONFIRMED`.

### 20.3 Exact anchors changed in Part II (twenty-two)

Each row is a replacement of V2 bytes. **Nothing else in V2 was altered.** Line numbers refer to **V2's own
numbering**, so every anchor is independently checkable against the frozen V2 file.

| # | V2 anchor | What changed |
|---|---|---|
| 1 | §4.1, LOW-6 row (V2 line 217) | Status reduced to `CORRECTED — QUALIFIED`; byte-confirmed basis stated |
| 2 | §5.1, AC-AUD-1 attribution (V2 lines 305—307) | Quotation withdrawn; paraphrase used (NV-5) |
| 3 | §5.25, LOW-6 block (V2 lines 669—687) | Rewritten on the actual bytes (C-V2-1) |
| 4 | §6.5, L1 predicate row (V2 line 786) | Predicate widened to `Name` **and** `Attribute` (C-V2-3) |
| 5 | §6.5, L2 predicate row (V2 line 787) | Bare-name `connect` form added (C-V2-3) |
| 6 | §6.5, L3 predicate row (V2 line 788) | Call-syntax scan stated over both forms (C-V2-3) |
| 7 | §6.6, guard-limits paragraph (V2 lines 813, 816) | Module-qualified form added to "can detect"; unrelated-binding caveat added (C-V2-3) |
| 8 | §8.2, carriers #4 and #5 (V2 lines 976, 977) | PC provenance corrected (NV-7) |
| 9 | §8.3, compliant-control row 3 (V2 line 1002) | "Never its value" withdrawn (NV-2) |
| 10 | §8.4, mask bound and query-parameter bullet (V2 lines 1022, 1026) | "Verbatim" qualified as `quote_plus`-encoded (NV-6) |
| 11 | §9.4, pooling-consequence paragraph (insertion after V2 line 1284; V2 lines 1285—1291 replaced) | Vector V3 named (NV-4) |
| 12 | §12, PT-16 row (V2 line 1499) | L1/L2 call-form coverage stated (C-V2-3) |
| 13 | §15, identifier-provenance note (inserted after V2 line 1574) | PC provenance stated (NV-7) |
| 14 | §15, PC-01…PC-08 rows (V2 lines 1603—1610) | Cross-references re-pointed to §8.2 #4/#5; labels corrected (C-V2-2, NV-7) |
| 15 | §15, LOW-6 row (V2 line 1628) | Status reduced to `QUALIFIED`; V3 section cited |
| 16 | §16.5, LOW status count (V2 line 1698) | Count corrected to match §4.1 (C-V2-1) |
| 17 | §16.6, G10 (V2 line 1707 only) | Both call forms and bounded examples added (C-V2-3) |
| 18 | §17, V3 clarifying banner (inserted before V2 line 1713) | States §17 is V2's record, not V3's |
| 19 | §19.1, LOW-6 row (V2 line 1888) | Status reduced to `QUALIFIED` |
| 20 | §19.2, PC provenance row (V2 line 1901) | Provenance stated (NV-7) |
| 21 | §19.3, correction-trace row 9 (V2 line 1918) | Three-asterisk claim superseded (C-V2-1) |
| 22 | V2 footer (V2 lines 1931—1934) | Replaced by V3's own consistent footer (§20.7) |

**Additions (not V2 edits):** Part I (§I.1…§I.7); the `## Part II — Carried-forward V2 body` heading; the Part II disambiguation banner; and the whole of Part III (§20.1–§20.7), which occupies the same replacement region as anchor 22. **AUDIT-DRIVEN CORRECTION (V4) — C-V3-3 / F-V3 / F-V4:** this note previously named only Part I and the banner; it now names the `## Part II` heading and Part III §20.1–§20.7, and it records that V3 additionally carried a **duplicated V2 title line at V3 line 137** (byte-identical to V3 line 138 and to V2 line 1), which V4 **deletes** (§21.3 anchor 1). These change no V2
content.

### 20.4 Operator decisions — D-1, D-2, D-3 and D-4 all remain OPEN

| ID | Decision | V3 status | Note |
|---|---|---|---|
| **D-1** | Alembic Branch A versus Branch B | **OPEN / BLOCKED** | Part II §11 preserved: the branches are mutually exclusive; only their intersection is mandatory until D-1; Branch A's zero-live-call row retained. **No branch selected.** |
| **D-2** | Target host OS and the deployment `PLATFORM_PROFILE` | **OPEN / BLOCKED** | Part II §9.3, §10.3 preserved: predicate parameterised; runner pin BLOCKED. **No platform selected.** |
| **D-3** | Mode provenance and the selected runtime/test contract | **OPEN** | Part II §7 preserved: O1/O2/O4 stated with five attributes each; O3 disallowed. **No option selected**; every recommendation tagged `DESIGN-RECOMMENDATION`. |
| **D-4** | Whether percent-encoded components are refused or accepted | **OPEN** | Part II §9.6 preserved: consequence stated; stricter `REFUSE` labelled a recommendation. **No policy selected**; PT-12 stays OPEN. |

**Every recommendation in this document is a `DESIGN-RECOMMENDATION`, never an operator decision.** Nothing in
V3 resolves any of D-1…D-4, and nothing implies a resolution.

### 20.5 V3 output identity, read-back verification and digest convention

- **Path:** `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V3.md` — **outside** the repository.
- **Pre-existing artifact at this path:** none. This gate's **first** operation was a listing of
  `/opt/data/output` (outside the repository); no file existed at this path, so the write created the file and
  **nothing was overwritten, renamed, moved or deleted**. This statement rests on an operation **this** gate
  performed and is a claim about this gate's own write target only.
- **Byte count and stored-file SHA-256:** read back from disk after the final write; **both are reported in the
  terminal response to WO-PRE-3-V3-DESIGN-CORRECTION and are NOT embedded here**, because a file cannot contain
  the digest of itself. The work order expressly requires the stored digest to be reported after read-back
  rather than claimed inside the artifact.
- **Series-convention digest (reproducible under a stated rule).** The rule: locate the single line in this
  document that begins with the literal `- **V3 SHA-256` and ends with `-hex field zeroed):**`; take the single
  64-hexadecimal-character token on the line **immediately following** that line; replace those 64 characters
  with `0`; hash the whole resulting file with SHA-256. The substitution is **length-preserving** (64 characters
  for 64) and the label line occurs **exactly once**. The value was re-derived from the file on disk after the
  final write. It is **not** the SHA-256 of the bytes on disk; the stored-file digest is reported in the
  terminal response and is not embedded here.
- **V3 SHA-256 (series convention — the designated 64-hex field zeroed):**
  `e748e8b80334a208086bd508c93a33f37cbdf3df0d03a45528064e2422d42efc`
- **Inputs neither overwritten nor modified:** V2 and the V2 audit are preserved at the identities verified in
  §I.2, and the six upstream reports at the identities in §I.3 — **all re-hashed from disk after the V3
  write, all unchanged.**

### 20.6 Deviations, evidence-access limitations and failed operations

- **DV-1 (Git, read-only).** Only narrowly scoped read-only Git commands were used — `git rev-parse
  --abbrev-ref HEAD`, `git rev-parse HEAD`, `git rev-parse refs/heads/main`, `git rev-parse
  refs/remotes/origin/main`, `git rev-list --left-right --count main...origin/main`, `git diff --cached
  --name-only`, `git stash list`, and `git status --porcelain=v1` (initial and final). **No** fetch, pull,
  ls-remote, push, branch, tag, merge, rebase, reset, clean, stash, add, checkout or switch. **The remote was
  never contacted.** No repository-root listing, no `find`, no `os.walk`, no recursive traversal, no broad glob.
- **DV-2 (protected path).** The protected path was observed **only** as its literal `git status --porcelain=v1`
  line. It was never opened, read, hashed, stat-ed, traversed, copied, moved or staged, and no size, inode,
  mtime or owner was obtained.
- **DV-3 (evidence-access limitation — material).** Under this work order's read restriction ("read the two
  named report files only"), this gate **did not re-read** the repository, the third-party library, or any other
  report. Every repository and third-party citation in Part II is therefore carried as **V2's** statement
  (`SOURCE-CONFIRMED` **by V2**) and is **not** re-asserted as `SOURCE-CONFIRMED` by V3. The two advisory items
  that depend on `PRE-3-INDEPENDENT-AUDIT.md` (NV-2, NV-5) are labelled `AUDIT-CONFIRMED` and `QUALIFIED`. This
  is a real limitation on the strength of those two dispositions and is stated rather than glossed.
- **DV-4 (rendering artifact).** This gate's console output distorts asterisk runs and some adjacent words.
  Every byte-critical conclusion in this document was therefore derived from **hexadecimal dumps and exact list
  comparisons**, never from displayed text (§I.6, §5.25). No artifact affected any file.
- **DV-5 (tooling artifact).** The code-execution sandbox that produced this report materialises its own
  **ephemeral** script under `/tmp/hermes_sandbox_<random>/script.py` and removes it with the sandbox. It is a
  tooling artifact, **outside** the repository, containing no credential and performing no repository write.
  Disclosed rather than omitted. No helper or evidence file was authored inside the repository.
- **DV-6 (deviation from the work order's literal wording — disclosed).** The work order's C-V2-1 bullet states
  "V1 line 1277 contains no asterisks". The measured bytes show line 1277 contains **eight** asterisks in four
  balanced pairs and **ends** with `authorization:`; the lone asterisk is on line 1278. V3 records the **byte
  truth** and does not repeat the literal bullet; the divergence is disclosed in §5.25 and here. The
  substantive correction required by C-V2-1 (withdraw the unsupported three-asterisk quotation; do not claim
  V2's front matter was corrected; make the footer consistent) is fully satisfied.
- **DV-7 (failed or inapplicable operations).** None. No command failed, no operation was blocked, no input
  identity mismatched, and no protected-path boundary was approached.
- **DV-8 (carried, unfixed, flagged).** V2 §19.3's cross-reference to a "§0" was a **dangling reference
  inside V2**. V3 does **not** edit V2's text for it; the flag is recorded here and in the Part II banner.

- **DV-9 (V3 breaks two of the thirteen V1-to-V2 byte-preservation blocks — disclosed).** The V2 audit
  verified that thirteen V1 line-ranges appear byte-identically in V2 (its §7). Two of those blocks contain
  text that the audit of V2 **required this pass to change**, so V3 necessarily no longer reproduces them
  verbatim: (i) **V1 lines 215–260** (V1 §5.1–§5.2) contains V1 lines **238–240**, the AC-AUD-1 passage
  edited for **NV-5** (§5.1); (ii) **V1 lines 459–488** (V1 §6.6) contains V1 lines **477** and **480**, the
  guard-limits wording edited for **C-V2-3** (§6.6). **The other eleven blocks are reproduced byte-identically
  in V3** (verified this pass). This is a consequence of the required corrections, not an incidental loss, and
  it is disclosed rather than hidden: a reader must not expect V3 to reproduce all thirteen blocks.
- **DV-10 (V2's statements about V1 section numbers).** V2's carried front matter states that V1's
  §5.1–§5.2 and §6.6 are "carried forward verbatim". That statement remains **true of V2** (Part II is V2's own
  text), but it is **no longer true of V3** for the two blocks named in DV-9. §I.4 and §20.3 govern in V3.
### 20.7 Authorization statement (V3 footer and gates)

**No implementation, test execution, repository mutation, publication or deployment was authorised by this work
order or performed by this gate.** This pass created exactly **one** file — this report — outside the
repository. It changed no repository file, test, CI workflow, configuration, migration, database or remote
state, and executed no test, import, engine construction, connection or migration. It resolved no operator
decision. The gates stated at the head of this document, and repeated immediately below, are unchanged and
remain **NOT GRANTED**.

**Implementation authorization:** NOT GRANTED
**Git commit / push authorization:** NOT GRANTED
**Production deployment authorization:** NOT GRANTED

**This document claims no acceptance of itself.** It is offered for independent re-audit pinned to its
stored-file SHA-256, reported in the terminal response and deliberately not embedded here (§20.5).

---

*End of PRE-3-CORRECTED-V3. READ ONLY — no implementation, no test execution, no repository modification, no CI change, no database operation, no migration, no publication, no deployment.*

*This document claims no acceptance of itself: it is offered for independent re-audit pinned to its stored-file SHA-256, which is reported in the terminal response to WO-PRE-3-V3-DESIGN-CORRECTION and is not embedded here (§20.5).*

*Operator decisions **D-1**, **D-2**, **D-3** and **D-4** remain OPEN — none decided, none implied.*

*Implementation authorization: NOT GRANTED.*

*Git commit / push authorization: NOT GRANTED.*

*Production deployment authorization: NOT GRANTED.*

*No implementation, test execution, repository mutation, publication or deployment was authorised by this work order or performed by this gate (§20.7). V2, V1 and every earlier report are preserved byte-for-byte at their verified identities (§I.2, §I.3, §20.5).*
## Part III — V4 corrections, change log and integrity record

### 21.1 Correction matrix — every mandatory correction and advisory this pass addresses

Statuses use the permitted vocabulary `CORRECTED — SOURCE-BYTE CONFIRMED`, `CORRECTED — QUALIFIED` and
`OPEN — EVIDENCE INSUFFICIENT`. **No item is marked resolved on wording alone**, and **no item is marked
`SOURCE-BYTE CONFIRMED` on evidence this pass did not measure.**

| Finding | Required disposition | V4 section that resolves it | Basis of verification in this pass | Status |
|---|---|---|---|---|
| **C-V3-1** (F-V1 — the "unterminated emphasis span" reading tagged as a byte fact) | Retag as `INTERPRETATION`; remove or justify "unterminated"; state the byte facts; reconcile §5.25, §20.2, the change log and every `SOURCE-BYTE FACT` claim; **do not infer an unclosed span from a trailing asterisk alone** | §5.25 (row for V1 line 1278; point 3 rewritten), §20.2 item 7 (byte facts) **+ new item 7a** (should be `INTERPRETATION`, withdrawn), §21.2 rows 3–5 and 11 | **Hex + `str.count` over V1 lines 1273–1278**, measured this pass: 1 + 8 + 1 = **10** asterisks, five balanced pairs, no blank line in the block | **CORRECTED — SOURCE-BYTE CONFIRMED** |
| **C-V3-2** (F-V2 — §20.2 item 8 misattributed) | Withdraw the claim that the three-asterisk form is only a console artifact; state the verified V1/V2 distinction; keep rendering artifacts separate from file bytes; correct dependent change-log statements | §20.2 item 8 restated; §21.2 rows 6 and 12 | **Hex of V2 lines 670 and 674** (each carries `2a2a2a`) against **V1 lines 13–15** (`2a2a` + text + `2a2a`) | **CORRECTED — SOURCE-BYTE CONFIRMED** |
| **C-V3-3** (F-V3 / F-V4 — undeclared structure changes) | Decide the duplicated title's fate (**prefer removal** if it alters no substantive evidence and does not invalidate the declared preservation method); declare all added structural elements, including `## Part II` and Part III §20.1–§20.6; update anchor accounting and the change log *(the `§20.1–§20.6` in this requirement column is a **verbatim quotation** of the earlier audit's wording; the resolution correctly documents `§20.1–§20.7`; `AUDIT-DRIVEN CORRECTION (V5)` — optional advisory)* | §21.3 anchor 1 (V3 line 137 **deleted**); §21.3 anchor 11 (§20.3 additions note corrected to name the `## Part II` heading and Part III §20.1–§20.7); §21.2 row 7 | **List equality**: V3 line 137 == V3 line 138 == V2 line 1; the additions note measured against the structure V3 actually has | **CORRECTED — DECLARED** (structure) / **SOURCE-BYTE CONFIRMED** (the equality) |
| **F-V5** (§20.3 rows 11 and 17) | Correct the declared ranges so they represent the bytes actually changed | §20.3 rows 11 and 17 (§21.3 anchors 9 and 10) | **`difflib.SequenceMatcher(None, V2_lines, V3_lines, autojunk=False)`**: row 11 = insertion after V2 line 1284 **+ replacement of V2 lines 1285–1291** (V2 lines 1283 and 1284 are byte-equal); row 17 = **V2 line 1707 only** (V2 lines 1706 and 1708 byte-equal) | **CORRECTED — SOURCE-BYTE CONFIRMED** |
| **F-V6** (§5.25 "throughout") | Describe the actual markup, given that the closing block uses single-asterisk italics | §5.25 (anchor 4); §21.2 row 10 | **`str.count` of asterisks on V3's footer lines**: gate lines (V3 2312–2314) carry 4 each (balanced `**…:**`); closing block (V3 2321–2333) uses single-asterisk italics, each line self-balanced | **CORRECTED — SOURCE-BYTE CONFIRMED** |
| **F-V7** (G10) | Qualify "closing BYPASS-1" so it cannot be read as proof of an implemented or tested runtime guard | §16.6 G10 (anchor 6) | This pass is **documentation-only**; no code was written, executed or tested, and this pass **claims none** | **CORRECTED — QUALIFIED** |
| **F-V8** (§15 provenance note) | Clarify that the superseded §15 references are historical, carried forward from V2, retained only to explain the correction; do not imply the superseded state is the active inventory | §15 note (anchor 5) | V3's own §8.2 carrier rows (#4/#5) and §15 rows, read in V3's bytes | **CORRECTED — QUALIFIED** |

**Preserved without re-grading — statuses carried forward, prose not byte-identical (explicit).** `C-V2-1`,
`C-V2-2`, `C-V2-3` and advisories `NV-2`, `NV-4`, `NV-5`, `NV-6`, `NV-7` are carried in Part II with the
**statuses V3 gave them — carried forward, not byte-identical prose**. The explanatory text around those
statuses is subject **only to the explicitly declared V4 anchors** of §21.3 (anchors 2, 3, 7 and 8 edit the
`C-V2-1` narrative at §5.25 and §20.2; anchor 5 edits the §15 provenance note inserted under `C-V2-2` / `NV-7`).
V4 neither upgrades nor downgrades the statuses and makes **no new source claim** about them.
`[AUDIT-DRIVEN CORRECTION (V5) — F-4B]`

**Deliberately not changed.** The `AUDIT-CONFIRMED` / `QUALIFIED` labelling of NV-2 and NV-5; V3's DV-6
divergence record; the retained limit lists in §6.6; the carried V2 statements about repository source; every
`DESIGN ADDRESSED — IMPLEMENTATION UNVERIFIED` status.

### 21.2 Change log — source-byte facts distinguished from interpretation

| # | Item | Class | Evidence |
|---|---|---|---|
| 1 | V1 lines 13–15 are `**…:** NOT GRANTED` — 4 asterisks each (two balanced pairs) | **SOURCE-BYTE FACT** | hex + `str.count` on V1 |
| 2 | V2 lines 15–17 are byte-identical to V1 lines 13–15 | **SOURCE-BYTE FACT** | list equality (`==`) returns `True` |
| 3 | V1 line 1277 carries 8 asterisks (four balanced pairs) and **ends** with `authorization:` — a colon, no asterisk | **SOURCE-BYTE FACT** | hex tail `…617574686f72697a6174696f6e3a`; `str.count` = 8 |
| 4 | V1 line 1278 is `NOT GRANTED.*` — one lone trailing asterisk | **SOURCE-BYTE FACT** | hex `4e4f54204752414e5445442e2a` |
| 5 | The asterisk inventory over V1 lines 1273–1278 is 1 + 8 + 1 = 10 — five balanced pairs — in one non-blank-separated paragraph | **SOURCE-BYTE FACT** | `str.count` per line + blank-line scan over V1 lines 1273–1278 |
| 6 | V2 lines 670 and 674 each contain a three-asterisk run `2a2a2a` inside **V2's own** quotation of V1's front matter, while V1 lines 13–15 do not | **SOURCE-BYTE FACT** | hex of V2 lines 670/674 and V1 lines 13–15 |
| 7 | V3 line 137 == V3 line 138 == V2 line 1 (the duplicated V2 title line) | **SOURCE-BYTE FACT** | list equality (`==`) returns `True` |
| 8 | §20.3 row 11's declared range vs the bytes: insertion after V2 line 1284; V2 lines 1285–1291 replaced; V2 lines 1283 and 1284 byte-equal | **SOURCE-BYTE FACT** | `difflib.SequenceMatcher`, no normalisation |
| 9 | §20.3 row 17's declared range vs the bytes: V2 line 1707 only; V2 lines 1706 and 1708 byte-equal | **SOURCE-BYTE FACT** | same alignment method |
| 10 | V4's own gates and footer: three gate lines in balanced `**…:**` (4 asterisks each) and a closing block of single-asterisk italics, each statement complete on one line and each line self-balanced | **SOURCE-BYTE FACT** | `str.count` on V4's own footer lines, at read-back (§21.5) |
| 11 | Reading the trailing `*` on V1 line 1278 as an **"unterminated emphasis span at end of file"** | **INTERPRETATION** — **not byte-obtainable, and WITHDRAWN**: the measured inventory (10 asterisks, five balanced pairs, one paragraph) shows the span opened at V1 line 1273 closes at V1 line 1278 | markdown emphasis semantics |
| 12 | This series' tooling distorts asterisk runs and some adjacent words in *displayed* output (observed this pass: a stored `` `authorization:` `` displayed as `` `authorization:*** ``) | **INTERPRETATION** of an observed tooling property — a **real artifact, kept strictly separate from file bytes** | observed in this pass's own console output; resolved by hex |
| 13 | The V3 and V3-audit input identities, and all eight upstream identities, reproduce from disk | **SOURCE-BYTE FACT** | fresh full-file SHA-256, this pass |
| 14 | `operator/entrypoint.py:53-60` interpolates the host value (`% host`) | **AUDIT-CONFIRMED — not read here** | V3 audit / V2 audit (NV-2) |
| 15 | AC-AUD-1's exact source wording | **AUDIT-CONFIRMED — not read here** | V3 audit / V2 audit (NV-5) |

**Every correction that rests on a byte comparison is proved from hex, `str.count` or list equality.** The two
items resting on a document outside this pass's authorised reading (14, 15) are labelled `AUDIT-CONFIRMED` and
are **not** presented as byte facts.

### 21.3 Exact anchors changed in Part II (eleven)

Each row is a change to V3's carried bytes. **Nothing else in V3 was altered.** Line numbers refer to **V3's
own numbering**, so every anchor is independently checkable against the frozen V3 file; the hunk structure is
reproducible with `difflib.SequenceMatcher(None, V3_lines, V4_PartII_lines, autojunk=False)`, no normalisation.

| # | V3 anchor (V3's own line numbers) | What changed | Finding |
|---|---|---|---|
| 1 | V3 line 137 | **Deleted** — a duplicated V2 title line, byte-identical to V3 line 138 and to V2 line 1. One copy is retained (the former V3 line 138). Removing it alters no substantive evidence and leaves the declared preservation method intact. | C-V3-3 / F-V3 |
| 2 | V3 line 830 | §5.25 row for V1 line 1278: the "unterminated emphasis span" reading replaced by the byte fact plus a pointer to the retagged interpretation. | C-V3-1 |
| 3 | V3 lines 850–852 | §5.25 point 3 restated on the bytes; the "unterminated emphasis span" wording and its `SOURCE-BYTE FACT` tag withdrawn. | C-V3-1 |
| 4 | V3 line 866 | §5.25 correction bullet: "balanced `**…**` throughout" corrected to balanced emphasis (`**` for the gate lines, `*` for the closing italic lines). | F-V6 |
| 5 | V3 lines 1773–1774 | §15 provenance note: the superseded references declared historical, carried forward from V2, retained only to explain the correction. | F-V8 |
| 6 | V3 line 1908 | §16.6 G10: "closing BYPASS-1" qualified as closure **at the specification level**, documentation only. | F-V7 |
| 7 | V3 line 2173 | §20.2 item 7 rewritten to state byte facts only; **one new row 7a inserted** immediately after it, recording the withdrawn reading as `INTERPRETATION`. | C-V3-1 |
| 8 | V3 line 2174 | §20.2 item 8 restated: the "console artifact, not file content" claim withdrawn; the V1/V2 byte distinction stated. | C-V3-2 / F-V2 |
| 9 | V3 line 2205 | §20.3 row 11: declared V2 range corrected to "insertion after V2 line 1284; V2 lines 1285–1291 replaced". | F-V5 |
| 10 | V3 line 2211 | §20.3 row 17: declared V2 range corrected to "V2 line 1707 only". | F-V5 |
| 11 | V3 line 2218 | §20.3 additions note: now declares the `## Part II` heading and Part III §20.1–§20.7, and records the deleted duplicate title. | C-V3-3 / F-V4 |

**Line-count effect of the anchors:** V3's **2333** content lines become **2348** in Part II (−1 deletion;
+11 at V3 850–852; +4 at V3 1773–1774; +1 at V3 2173; the remaining anchors are one-for-one replacements).

**Additions in V4 (not V3 edits):** V4's own **header block** (V4's own line numbering, lines **1–16**: title
line 1; cover metadata lines 3–9 — document type, work order, mode, repository, branch, supersedes and
new-artifact; and the three **authorization-gate lines 13–15**), Part I (§I.1–§I.7), the
`## Part II — Carried-forward V3 body` heading, the Part II disambiguation banner, and the whole of Part III
(§21.1–§21.7). §21.7 refers to the gates stated at the head of this document, so no gate is hidden. The three
gate lines are **restrictive controls** (`NOT GRANTED`); they do **not** authorise implementation and imply no
permission of any kind. These additions change no V3 content.  `[AUDIT-DRIVEN CORRECTION (V5) — F-4A]`

### 21.4 Operator decisions — D-1, D-2, D-3 and D-4 all remain OPEN

| ID | Decision | V4 status | Note |
|---|---|---|---|
| **D-1** | Alembic Branch A versus Branch B | **OPEN / BLOCKED** | Part II §11 and §20.4 preserved: the branches are mutually exclusive; only their intersection is mandatory until D-1. **No branch selected.** |
| **D-2** | Target host OS and the deployment `PLATFORM_PROFILE` | **OPEN / BLOCKED** | Part II §9.3 and §10.3 preserved: the predicate stays parameterised and the CI runner pin stays BLOCKED. **No platform selected.** |
| **D-3** | Mode provenance and the selected runtime/test contract | **OPEN** | Part II §7 preserved: O1/O2/O4 stated with five attributes each; O3 disallowed. **No option selected**; every recommendation tagged `DESIGN-RECOMMENDATION`. |
| **D-4** | Whether percent-encoded components are refused or accepted | **OPEN** | Part II §9.6 preserved: the consequence is stated; the stricter `REFUSE` is labelled a **recommendation**. **No policy selected**; PT-12 stays OPEN. |

**Every recommendation in this document is a `DESIGN-RECOMMENDATION`, never an operator decision.** Nothing in
V4 resolves any of D-1…D-4, and nothing implies a resolution. **No migration branch, no target platform
profile, no runtime/test contract and no percent-encoding policy is selected by this pass.**

### 21.5 V4 output identity, read-back verification and digest convention

- **Path:** `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V4.md` — **outside** the repository.
  Existence was checked **before** the write (`os.path.exists → False`); no file existed at this path, so the
  write created the file and **nothing was overwritten, renamed, moved or deleted**.
- **Byte count and stored-file SHA-256:** read back from disk after the write; **both are reported in the
  terminal response to WO-PRE-3-V4-DESIGN-CORRECTION and are NOT embedded here**, because a file cannot
  contain the digest of itself.
- **Series-convention digest (reproducible under a stated rule).** The rule: locate the **single** line in
  this document that begins with the literal `- **V4 SHA-256` and ends with `-hex field zeroed):**`; take the
  single 64-hexadecimal-character token on the line **immediately following** that line; replace those 64
  characters with `0`; hash the whole resulting file with SHA-256. The substitution is **length-preserving**
  (64 characters for 64) and the label line occurs **exactly once**. It is **not** the SHA-256 of the bytes on
  disk; the stored-file digest is reported in the terminal response and is not embedded here.
- **V4 SHA-256 (series convention — the designated 64-hex field zeroed):**
  `ad403ab0cd668aedc1bf9ef4f7dc4b02a04100c5c26001b2ea3611b304d13443`
- **Inputs neither overwritten nor modified:** V3 and the V3 audit are preserved at the identities verified in
  §I.2, and the eight upstream reports at the identities in §I.3 — **all re-hashed from disk after the V4
  write, all unchanged.**

### 21.6 Deviations, evidence-access limitations and failed operations

- **DV-1 (partial read of V1 and V2 — disclosed).** The mandatory corrections require the actual bytes of V1
  and V2, so this pass read **only** V1 lines 13–15 and 1273–1278, and V2 lines 15–17, 670, 674, 1283–1291 and
  1706–1708, plus a full-file SHA-256 of both (to prove non-modification) and the headers needed to number
  those lines. No other content of V1 or V2 was read; **neither file was modified** (re-hashed, unchanged).
- **DV-2 (repository and source not accessed — material).** This work order is **documentation-only**. The
  repository was **not** entered, listed, stat-ed or read; **no Git command was run by this pass**; the branch
  and baseline shown in the header are **carried from V3**, not re-observed. Application and third-party
  source was **not** read. Every such citation in Part II remains V3's (or V2's) statement.
- **DV-3 (evidence-access limitation).** The two advisory items that depend on `PRE-3-INDEPENDENT-AUDIT.md`
  (NV-2, NV-5) remain `AUDIT-CONFIRMED` / `QUALIFIED` in Part II and are **not** upgraded by V4.
- **DV-4 (rendering artifact).** This gate's console output distorted asterisk runs and some adjacent words
  (observed: a stored `` `authorization:` `` displayed as `` `authorization:*** ``). Every byte-critical
  conclusion was derived from **hexadecimal dumps, `str.count` or exact list comparisons**, never from
  displayed text (§I.6). No file was affected.
- **DV-5 (tooling artifact).** The code-execution sandbox materialises its own **ephemeral** script and staged
  intermediates under `/tmp` (outside the repository) and removes them with the sandbox. Tooling artifacts
  only: no credential, no repository write.
- **DV-6 (no failed operation reached any artifact). — `AUDIT-DRIVEN CORRECTION (V5)` — F-4C:** the original
  heading read "no failed operations" and contradicted the `NameError` disclosed below; it is corrected here to
  this narrower, accurate claim. **No failure of this gate reached any artifact.** No operation whose result
  reached an artifact failed, and no protected-path boundary was approached. **The protected path was not observed,
  opened, read, hashed, stat-ed, traversed, copied, moved or staged at all**, because this pass ran no Git command
  and performed no repository listing. *(One non-material failure is disclosed and not concealed: an initial attempt
  to compute the upstream identities failed with a `NameError` in the pass's own throwaway script; it was corrected
  and re-run within the same pass, and **no artifact was affected.** The correction is an **author-session claim**
  of this gate and was not independently re-observed. It affected no file.)*
- **DV-7 (carried, unfixed, flagged).** V3's §20.6 DV-8 (V2 §19.3's dangling "§0" cross-reference) and V3's
  DV-9 / DV-10 (the two broken V1→V2 preservation blocks) are carried **unchanged**; V4 edits no Part II text
  for them.
- **DV-8 (document structure).** Part II ends with **V3's own footer** (§20.7 of V3), because Part II carries
  V3 in full. V4's own gates are stated at the head of this document and repeated in §21.7. **Both footers are
  internally consistent**, each within its own pass, and **neither is V4's stored digest**.

### 21.7 Authorization statement (V4 footer and gates)

**No implementation, test execution, repository mutation, publication or deployment was authorised by this work
order or performed by this pass.** This pass created exactly **one** file — this report — outside the
repository. It changed no repository file, test, CI workflow, configuration, migration, database or remote
state, and executed no test, import, engine construction, connection or migration. It resolved no operator
decision. The gates stated at the head of this document, and repeated immediately below, are unchanged and
remain **NOT GRANTED**.

**Markup note (measured on this file — §21.2 row 10).** The three gates immediately below use **balanced
`**…:**`** (two asterisks each side, four per line). The closing block that follows uses **single-asterisk
italics**, with **each statement complete on one line** and **each line self-balanced**. Neither block contains
a trailing or dangling asterisk, and neither contradicts this change log.

**Implementation authorization:** NOT GRANTED
**Git commit / push authorization:** NOT GRANTED
**Production deployment authorization:** NOT GRANTED

**This document claims no acceptance of itself.** It is offered for independent re-audit pinned to its
stored-file SHA-256, reported in the terminal response and deliberately not embedded here (§21.5).

---

*End of PRE-3-CORRECTED-V4. READ ONLY — no implementation, no test execution, no repository modification, no CI change, no database operation, no migration, no publication, no deployment.*

*This document claims no acceptance of itself: it is offered for independent re-audit pinned to its stored-file SHA-256, which is reported in the terminal response to WO-PRE-3-V4-DESIGN-CORRECTION and is not embedded here (§21.5).*

*Operator decisions **D-1**, **D-2**, **D-3** and **D-4** remain OPEN — none decided, none implied.*

*Implementation authorization: NOT GRANTED.*

*Git commit / push authorization: NOT GRANTED.*

*Production deployment authorization: NOT GRANTED.*

*No implementation, test execution, repository mutation, publication or deployment was authorised by this work order or performed by this pass (§21.7). V3, V2, V1 and every earlier report are preserved byte-for-byte at their verified identities (§I.2, §I.3, §21.5).*

## Part III — V5 corrections, change log and integrity record

### 22.1 Correction matrix — every finding this pass addresses

Statuses use the permitted vocabulary `CORRECTED — DECLARED`, `CORRECTED — QUALIFIED` and
`OPEN — EVIDENCE INSUFFICIENT`. **No item is marked resolved on wording alone**, and **no item is marked
`SOURCE-BYTE CONFIRMED` on evidence this pass did not measure.**

| Finding | Required disposition | V5 section that resolves it | Basis of verification in this pass | Status |
|---|---|---|---|---|
| **F-4A** (C-4-1 — incomplete additions inventory) | Amend §21.3's additions inventory so V4's own header block is explicitly accounted for; identify lines 1–16 and the authorization-gate lines 13–15; preserve the §21.7 reference to the gates at the head of the document; do not imply that the gates authorise implementation; keep the change to accurate change accounting | **§22.3 anchor 1** — §21.3 additions note (V4 lines 2571–2572) rewritten | Structure check against the carried V4 bytes: Part I / Part II / Part III heading sets and the three gate lines exist at the stated V4 line numbers; the gate lines are restrictive (`NOT GRANTED`, 4 asterisks each by `str.count`) | **CORRECTED — DECLARED** (inventory) |
| **F-4B** (C-4-2 — overbroad "unchanged" wording) | Distinguish unchanged dispositions/statuses from edited explanatory prose; state that the prior statuses are carried forward and the explanatory text is subject only to the explicitly declared anchors; preserve the scope of V4's eleven declared anchors; do not claim all prose is unchanged | **§22.3 anchors 2 and 3** — §I.4 "Preserved" paragraph (V4 lines 74–77) and §21.1 "Preserved without re-grading" paragraph (V4 lines 2516–2518) rewritten | §21.3's declared anchors 2, 3, 7 and 8 lie inside the `C-V2-1` narrative and anchor 5 inside the `C-V2-2` / `NV-7` note — as the V4 audit itself established (inherited finding, not re-derived here) | **CORRECTED — QUALIFIED** |
| **F-4C** (C-4-3 — DV-6 internal contradiction) | Correct the DV-6 heading so it does not contradict the disclosed `NameError`; preserve the facts that the script failed, was corrected and re-run; preserve that no artifact was affected; do not conceal the `NameError`; do not claim the correction was independently observed | **§22.3 anchor 4** — §21.6 DV-6 bullet (V4 lines 2626–2630) retitled and reworded | V4's own disclosed text (V4 lines 2629–2630) carries the `NameError`; V5 records it as an **author-session claim** of the V4 gate and does not present it as re-observed | **CORRECTED — QUALIFIED** |
| *(optional advisory, §5 of the work order)* §21.1 `C-V3-3` requirement cell | Optionally mark the quoted requirement as a quotation, without changing the quoted requirement itself | **§22.3 anchor 5** — §21.1 `C-V3-3` row (V4 line 2510) annotated with the `AUDIT-DRIVEN CORRECTION (V5)` marker | The requirement cell quotes the earlier audit's `§20.1–§20.6`; the resolution documents `§20.1–§20.7` — both carried unaltered | **CORRECTED — QUALIFIED** (optional) |

**Preserved without re-grading (explicit).** The V4 dispositions of `C-V2-1`, `C-V2-2`, `C-V2-3` and advisories
`NV-2`, `NV-4`, `NV-5`, `NV-6`, `NV-7` are carried in Part II with the **statuses V4 gave them — carried
forward, not byte-identical prose** (see §22.3 and the corrected §21.1 paragraph). V5 neither upgrades nor
downgrades them and makes **no new source claim** about them.

**No V5 verdict.** V5 states no audit verdict of its own; the V4 re-audit's `ACCEPTED WITH CONDITIONS` and every
earlier verdict are carried as **historical**, at the grade their own passes gave them.

**Historical (V4's own) accounting, carried unchanged.** V4's mandatory corrections `C-V3-1`, `C-V3-2`, `C-V3-3`
and its advisories `F-V5`, `F-V6`, `F-V7`, `F-V8` are **not** re-adjudicated here: their statuses are carried in
Part II at §21.1 / §21.2 / §21.3 exactly as V4 recorded them, and the V4 re-audit's verdict on them is carried
as history.

### 22.2 Change log — source-byte facts distinguished from interpretation

| # | Item | Class | Evidence |
|---|---|---|---|
| 1 | The V4 and V4-audit input identities reproduce from disk | **SOURCE-BYTE FACT** | fresh full-file SHA-256, this pass |
| 2 | All ten earlier upstream identities reproduce from disk | **SOURCE-BYTE FACT** | fresh full-file SHA-256 per file, this pass |
| 3 | V5's output path held no pre-existing file before the write | **AUTHOR-SESSION CLAIM** of this pass | `os.path.exists → False`, measured immediately before the write |
| 4 | The three authorization-gate lines at the head of this document are restrictive (`NOT GRANTED`) and carry 4 asterisks each (balanced) | **SOURCE-BYTE FACT** | hex + `str.count` on this file, at read-back (§22.5) |
| 5 | This series' tooling distorts asterisk runs and some adjacent characters in *displayed* text | **INTERPRETATION** of an observed tooling property — a **real artifact, kept strictly separate from file bytes** | observed in this pass's own console output; resolved by hex |
| 6 | V4's eleven declared anchors describe **V4's edits to V3**; V5's five anchors describe **V5's edits to V4**. The two accountings are separate and neither is claimed to be the other | **SOURCE-BYTE FACT** | V4's §21.3 table carried byte-unchanged in Part II; V5's anchors enumerated in §22.3 |
| 7 | `operator/entrypoint.py:53-60` interpolates the host value, and AC-AUD-1's exact source wording, are as carried | **AUDIT-CONFIRMED — not read here** | carried: V4 §21.2 rows 14 and 15 |
| 8 | The V4-audit artifact at the named path is 43766 bytes and hashes to the 64-character value `65f18dcb…be2a1a2c675f0`; the work order's expected digest for it is **63 hex characters** — one digit short of a valid SHA-256 (`DV-0`) | **SOURCE-BYTE FACT** (the measurement) / **TRANSPORT-ANOMALY NOTE** (the malformed expectation) | `os.path.getsize` + full-file SHA-256 against the stated value, this pass |

**Every correction that rests on a byte comparison is proved from hex, `str.count` or list equality.** Items
resting on a document outside this pass's authorised reading (row 7) are labelled `AUDIT-CONFIRMED` and are **not**
presented as byte facts.

### 22.3 Exact anchors changed in Part II (five)

Each row is a change to V4's carried bytes. **Nothing else in V4 was altered.** Line numbers refer to **V4's own
numbering**, so every anchor is independently checkable against the frozen V4 file; the hunk structure is
reproducible with `difflib.SequenceMatcher(None, V4_lines, V5_PartII_lines, autojunk=False)`, no normalisation.

**These five anchors are V5's own documentary corrections. They are NOT part of V4's historical eleven anchors**,
which are a different, earlier set declared in §21.3 (carried byte-unchanged in Part II) and which account for
V4's edits to V3. The two accountings are separate: §21.3 accounts for the **V4→V3** changes; §22.3 accounts for
the **V5→V4** changes.

| # | V4 anchor (V4's own line numbers) | What changed | Finding |
|---|---|---|---|
| 1 | V4 lines 2571–2572 | §21.3 additions note extended to name V4's own header block (lines 1–16, including the three authorization-gate lines 13–15), to preserve the §21.7 reference to the gates at the head of the document, and to state that the gate lines are restrictive controls that do not authorise implementation. | F-4A / C-4-1 |
| 2 | V4 lines 74–77 | §I.4 "Preserved unchanged (explicitly)" restated: the prior dispositions and statuses are carried forward, while the explanatory prose is subject only to the explicitly declared V4 anchors of §21.3 (anchors 2, 3, 5, 7 and 8 named). | F-4B / C-4-2 |
| 3 | V4 lines 2516–2518 | §21.1 "Preserved without re-grading (explicit)" restated on the same basis. | F-4B / C-4-2 |
| 4 | V4 lines 2626–2630 | §21.6 DV-6 retitled ("no failed operation reached any artifact") and reworded so its headline no longer contradicts its own disclosed `NameError`; the `NameError`, its correction and its re-run are preserved and marked an author-session claim. | F-4C / C-4-3 |
| 5 | V4 line 2510 | §21.1 `C-V3-3` requirement cell: a minimal quotation annotation added **outside** the quoted requirement, carrying the `AUDIT-DRIVEN CORRECTION (V5)` marker (optional advisory). | optional advisory |

**Line-count effect of the anchors:** V4's **2673** content lines become **2691** in Part II — anchor 1: 2 → 7 (+5); anchor 2: 4 → 9 (+5); anchor 3: 3 → 7 (+4); anchor 4: 5 → 9
(+4); anchor 5: 1 → 1 (+0); net **+18**. The arithmetic is 2673 + 5 + 5 + 4 + 4 + 0 = 
**2691**.
**Anchor-boundary confirmation.** The five anchors are the only places where V5's Part II differs from V4's bytes:
each anchor was applied to an exactly bounded V4 line range, and every V4 byte outside those ranges is carried
verbatim. A `difflib` alignment over the frozen V4 file and V5's Part II region returns exactly five non-equal
hunks, one per anchor, with no residue.

**Additions in V5 (not V4 edits):** V5's own **header block** (this file, lines **1–16**: title line 1; cover
metadata lines 3–9; and the three **authorization-gate lines 13–15**), Part I (§I.1–§I.7), the
`## Part II — Carried-forward V4 body` heading, the Part II disambiguation banner (V5), and the whole of Part III
(§22.1–§22.7). The three gate lines are **restrictive controls**; they do **not** authorise implementation. They
change no V4 content outside the five anchors above. **V5 does not claim that any of its edits were part of V4's
original eleven anchors.**

### 22.4 Operator decisions — D-1, D-2, D-3 and D-4 all remain OPEN

| ID | Decision | V5 status | Note |
|---|---|---|---|
| **D-1** | Alembic Branch A versus Branch B | **OPEN / BLOCKED** | Part II §11, §20.4 and §21.4 preserved: the branches are mutually exclusive; only their intersection is mandatory until D-1. **No branch selected.** |
| **D-2** | Target host OS and the deployment `PLATFORM_PROFILE` | **OPEN / BLOCKED** | Part II §9.3, §10.3 and §21.4 preserved: the predicate stays parameterised and the CI runner pin stays BLOCKED. **No platform selected.** |
| **D-3** | Mode provenance and the selected runtime/test contract | **OPEN** | Part II §7 and §21.4 preserved: O1/O2/O4 stated with five attributes each; O3 disallowed. **No option selected**; every recommendation tagged `DESIGN-RECOMMENDATION`. |
| **D-4** | Whether percent-encoded components are refused or accepted | **OPEN** | Part II §9.6 and §21.4 preserved: the consequence is stated; the stricter `REFUSE` is labelled a **recommendation**. **No policy selected**; PT-12 stays OPEN. |

**Every recommendation in this document is a `DESIGN-RECOMMENDATION`, never an operator decision.** Nothing in
V5 resolves any of D-1…D-4, and nothing implies a resolution. **No migration branch, no target platform profile,
no runtime/test contract and no percent-encoding policy is selected by this pass.**

### 22.5 V5 output identity, read-back verification and digest convention

- **Path:** `/opt/data/output/PRE-3-CORRECTED-DESIGN-AND-RECONCILIATION-V5.md` — **outside** the repository.
  Existence was checked **before** the first write (`os.path.exists → False`); the file was then **re-generated once
  within this pass** (§22.6 DV-11). **No pre-existing file was overwritten, renamed, moved or deleted**, and the
  delivered bytes are those measured for the terminal response.
- **Byte count and stored-file SHA-256:** read back from disk after the write and re-measured; **both are
  reported in the terminal response to WO-PRE-3-V5-DOCUMENTARY-CORRECTION and are NOT embedded here**, because a
  file cannot contain the digest of itself. The read-back re-measurement was performed **by this pass** on its own
  output; **no independent verification of the stored-file digest is claimed here.**
- **Series-convention digest (reproducible under a stated rule — inherited convention preserved unchanged).** The
  rule: locate the **single** line in this document that begins with the literal `- **V5 SHA-256` and ends with
  `-hex field zeroed):**`; take the single 64-hexadecimal-character token on the line **immediately following**
  that line; replace those 64 characters with `0`; hash the whole resulting file with SHA-256. The substitution is
  **length-preserving** (64 characters for 64) and the label line occurs **exactly once**. It is **not** the
  SHA-256 of the bytes on disk; the stored-file digest is reported in the terminal response and is not embedded
  here. The convention is inherited from V2/V3/V4 without improvised variation; the three carried labels
  (`- **V4 SHA-256 …`, `- **V3 SHA-256 …`, `- **SHA-256 …`) are **not** selectable by it.
- **V5 SHA-256 (series convention — the designated 64-hex field zeroed):**
  `66a76cdbd57a704ac69245fff8a373d57741ecee80f65ed6ecb9f40c73eaef51`
- **Inputs neither overwritten nor modified:** V4 and the V4 audit are preserved at the identities verified in
  §I.2, and every upstream report at the identities in §I.3 — **all re-hashed from disk after the V5 write, all
  unchanged.**

### 22.6 Deviations, evidence-access limitations and failed operations

- **DV-0 (input-identity anomaly — flagged, disclosed, not silently passed).** The work order's stated expected
  SHA-256 for the V4 audit is 63 hexadecimal characters — one short of a valid SHA-256 — and equals the measured
  on-disk digest with exactly one character deleted (position 54, hex `2`). The artifact at the exact named path is
  43766 bytes — the stated byte count — and hashes to
  `65f18dcb398e5e12c6bb5dc98f82a9d5f13f2f6b1fea944fffbbe2a1a2c675f0`. The input is treated as the exact named
  artifact (path + exact byte count + all-but-one digest character); **no other artifact was substituted**, and the
  anomaly is **not** reported as a clean `2 / 2 MATCH` (§I.2).
- **DV-1 (reading scope — bounded).** This pass read **only** V4 and the V4 audit (both in full, at their verified
  identities) and the region of its own output. **V1, V2 and V3 were not read at all** — the three findings are
  internal-consistency matters of V4's own change documentation and require none of their bytes. Every other
  artifact in §I.3 was **hashed only**, to reproduce its identity; its content was not read.
- **DV-2 (repository and source not accessed — material).** This work order is **documentation-only**. The
  repository was **not** entered, listed, stat-ed or read; **no Git command was run by this pass**; the branch and
  baseline shown in the header are **carried from V4**, not re-observed. Application and third-party source was
  **not** read. Every such citation in Part II remains V4's (or V3's, or V2's) statement.
- **DV-3 (evidence-access limitation).** The items that depend on `PRE-3-INDEPENDENT-AUDIT.md` (`NV-2`, `NV-5`)
  remain `AUDIT-CONFIRMED` / `QUALIFIED` in Part II and are **not** upgraded by V5.
- **DV-4 (rendering artifact).** This gate's console output distorted asterisk runs and some adjacent characters
  (a stored bold or italic run, or a plain colon or closing backtick, shown with a spurious additional asterisk).
  Every byte-critical conclusion was derived from **hexadecimal dumps, `str.count` or exact list comparisons**,
  never from displayed text (§I.6). No file was affected.
- **DV-5 (tooling artifact).** The code-execution sandbox materialises its own **ephemeral** script and staged
  intermediates under `/tmp` (outside the repository) and removes them with the sandbox. The bounded builder used
  by this pass was placed **outside the repository**, in the output directory, and removed after use; a dry-run
  preview was written under `/tmp` (outside the repository) and removed as well. Tooling artifacts only: no
  credential, no repository write.
- **DV-6 (no failed operation reached any artifact).** **No failure of this pass reached any artifact**, and no
  protected-path boundary was approached. **The protected path was not observed, opened, read, hashed, stat-ed,
  traversed, copied, moved or staged at all**, because this pass ran no Git command and performed no repository
  listing. *(Non-material items are disclosed here rather than concealed, exactly as finding F-4C requires:
  (i) `DV-0`, the malformed expected V4-audit digest — an input-side anomaly, not a failure of this pass;
  (ii) one pre-write validation run of this pass's own throwaway builder that exited early because the expected
  V4-audit digest had been mis-typed inside that builder; and (iii) a later run of the same builder that stopped on
  a mis-specified internal assertion of that builder. Items (ii) and (iii) were each corrected within the same
  pass, **before any file was written**, and **no artifact was affected**; those corrections are author-session
  claims of this pass and were not independently re-observed. V4's own §21.6 DV-6 read "no failed operations"
  while disclosing a `NameError` — finding F-4C; that V4 disclosure is carried in Part II with the V4 heading
  corrected by §22.3 anchor 4, and is additionally recorded here as an inherited **author-session claim**, not as a
  fact this pass re-derived.)*
- **DV-7 (carried, unfixed, flagged).** V4's §21.6 DV-7 and DV-8 records are carried **unchanged**; V5 edits no
  Part II text for them.
- **DV-8 (document structure).** Part II ends with **V4's own footer** (§21.7 of V4), because Part II carries V4 in
  full. V5's own gates are stated at the head of this document and repeated in §22.7. **Both footers are
  internally consistent**, each within its own pass, and **neither is V5's stored digest**.
- **DV-9 (inherited process claims).** V4's §21.5 pre-write existence check and V4's §21.6 DV-6 `NameError`
  disclosure are claims about the **V4 gate's own session**; they cannot be re-derived by this pass and are
  carried as **author-session claims** (§I.5), not as independently verified facts.
- **DV-10 (no scope expansion).** No unrelated wording, error or inherited claim was silently repaired: every
  edit made by this pass is one of the five declared anchors of §22.3, each tied to a named finding, and the one
  optional advisory was applied only because a minimal, unambiguous quotation annotation was useful (§5 of the
  work order). No inherited audit finding was reclassified.
- **DV-11 (own-output regeneration — disclosed).** The V5 file was written once and then **re-generated once within
  this same pass**, after this pass detected a marker-consistency gap in its own newly authored text (the §22.3
  anchor-5 passage initially lacked the `AUDIT-DRIVEN CORRECTION (V5)` marker that the Part II banner promises).
  The removed copy was this pass's **own just-created output**, verified by its digest before removal; **no
  pre-existing artifact was overwritten, renamed, moved or deleted**, and every figure in this document (line
  counts, the series digest) was re-derived from the final bytes.

### 22.7 Authorization statement (V5 footer and gates)

**No implementation, test execution, repository mutation, publication or deployment was authorised by this work
order or performed by this pass.** This pass created exactly **one** file — this report — outside the repository.
It changed no repository file, test, CI workflow, configuration, migration, database or remote state, and executed
no test, import, engine construction, connection or migration. It resolved no operator decision. The gates stated
at the head of this document, and repeated immediately below, are unchanged and remain **NOT GRANTED**. V5 makes
**no claim that any guard has been implemented or tested**; finding F-V7's specification-level qualification,
carried in Part II at §16.6 G10, remains in force.

**Grant-token accounting (measured on this file).** The US-spelled uppercase grant token occurs **twice** in this
document: once inside the mandated restrictive closing boundary line, and once inside the inherited condition
quoted in this sentence. **There is no permissive authorization statement anywhere in this document** — every
grant statement reads `NOT GRANTED`. The inherited condition — no operative grant, i.e. `AUTHORIZED` (US,
operative) `= 0` — is therefore preserved in its intended sense; the two occurrences above are restrictive or
meta-referential, never permissive.

**Markup note (measured on this file — §22.2 row 4).** The three gates immediately below use **balanced
`**…:**`** (two asterisks each side, four per line). The closing block that follows uses **single-asterisk
italics**, with **each statement complete on one line** and **each line self-balanced**. Neither block contains a
trailing or dangling asterisk, and neither contradicts this change log.

**Implementation authorization:** NOT GRANTED
**Git commit / push authorization:** NOT GRANTED
**Production deployment authorization:** NOT GRANTED

**This document claims no acceptance of itself.** It is offered for independent re-audit pinned to its
stored-file SHA-256, reported in the terminal response and deliberately not embedded here (§22.5).

---

*End of PRE-3-CORRECTED-V5. READ ONLY — no implementation, no test execution, no repository modification, no CI change, no database operation, no migration, no publication, no deployment.*

*This document claims no acceptance of itself: it is offered for independent re-audit pinned to its stored-file SHA-256, which is reported in the terminal response to WO-PRE-3-V5-DOCUMENTARY-CORRECTION and is not embedded here (§22.5).*

*Operator decisions **D-1**, **D-2**, **D-3** and **D-4** remain OPEN — none decided, none implied.*

*Implementation authorization: NOT GRANTED.*

*Git commit / push authorization: NOT GRANTED.*

*Production deployment authorization: NOT GRANTED.*

*No implementation, test execution, repository mutation, publication or deployment was authorised by this work order or performed by this pass (§22.7). V4, V3, V2, V1 and every earlier report are preserved byte-for-byte at their verified identities (§I.2, §I.3, §22.5).*

IMPLEMENTATION NOT AUTHORIZED. D-1 THROUGH D-4 REMAIN OPEN.
