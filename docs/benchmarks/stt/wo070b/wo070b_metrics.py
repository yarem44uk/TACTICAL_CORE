"""WO-070B benchmark-local Levenshtein metrics (WER / CER).

No production dependency is introduced: a small deterministic Levenshtein
alignment is implemented here.

Definitions (WO-070B §14):

    WER = (substitutions + deletions + insertions) / reference_word_count
    CER = (substitutions + deletions + insertions) / reference_character_count

Costs are unit costs (match 0, substitution 1, deletion 1, insertion 1), so
(substitutions + deletions + insertions) always equals the plain edit distance.

Determinism: the DP cost matrix is computed first; the operation counts are then
recovered by a single backtrack with a FIXED preference order:

    match (diagonal, costs nothing)
    > substitution (diagonal, costs 1)
    > deletion (reference character not matched — moves i)
    > insertion (hypothesis character not matched — moves j)

Because unit-cost alignments are not unique, this fixed order is what makes the
S/D/I split — and therefore every reported number — reproducible byte-for-byte.

Empty reference handling: a metric is undefined when the reference denominator is
0 (no reference words / no reference characters). In that case the function
returns None and the record is EXCLUDED by the caller, never scored as 0 or 1.
"""

METRICS_ID = "wo070b-levenshtein-v1"


def align_ops(reference, hypothesis):
    """Return (substitutions, deletions, insertions) for two sequences.

    ``reference`` and ``hypothesis`` are sequences (lists/strings) of units
    (words for WER, characters for CER).
    """
    n = len(reference)
    m = len(hypothesis)

    # dp[i][j] = edit distance between reference[:i] and hypothesis[:j]
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        ri = reference[i - 1]
        for j in range(1, m + 1):
            cost_sub = 0 if ri == hypothesis[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost_sub,  # match / substitution
                dp[i - 1][j] + 1,             # deletion
                dp[i][j - 1] + 1,             # insertion
            )

    subs = dels = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and reference[i - 1] == hypothesis[j - 1] \
                and dp[i][j] == dp[i - 1][j - 1]:
            i -= 1
            j -= 1
            continue
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            subs += 1
            i -= 1
            j -= 1
            continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dels += 1
            i -= 1
            continue
        if j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            ins += 1
            j -= 1
            continue
        raise AssertionError("unreachable alignment state")

    return subs, dels, ins


def wer(reference_tokens, hypothesis_tokens):
    """Word Error Rate. Returns None when the reference word count is 0."""
    ref_count = len(reference_tokens)
    if ref_count == 0:
        return None
    subs, dels, ins = align_ops(list(reference_tokens), list(hypothesis_tokens))
    return {
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
        "reference_count": ref_count,
        "wer": (subs + dels + ins) / ref_count,
    }


def cer(reference_chars, hypothesis_chars):
    """Character Error Rate. Returns None when the reference char count is 0."""
    ref_count = len(reference_chars)
    if ref_count == 0:
        return None
    subs, dels, ins = align_ops(list(reference_chars), list(hypothesis_chars))
    return {
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
        "reference_count": ref_count,
        "cer": (subs + dels + ins) / ref_count,
    }


def score_pair(reference_text, hypothesis_text, normalize_module):
    """Normalize both sides and score one (reference, hypothesis) pair.

    Returns a dict with normalized forms, per-record word/char op counts and the
    WER/CER values (None if the corresponding denominator is 0).
    """
    ref_norm = normalize_module.normalize_text(reference_text)
    hyp_norm = normalize_module.normalize_text(hypothesis_text)

    ref_tokens = ref_norm.split(" ") if ref_norm else []
    hyp_tokens = hyp_norm.split(" ") if hyp_norm else []
    ref_chars = ref_norm.replace(" ", "")
    hyp_chars = hyp_norm.replace(" ", "")

    word_ops = wer(ref_tokens, hyp_tokens)
    char_ops = cer(ref_chars, hyp_chars)

    return {
        "reference_normalized": ref_norm,
        "hypothesis_normalized": hyp_norm,
        "substitutions": (word_ops or {}).get("substitutions"),
        "deletions": (word_ops or {}).get("deletions"),
        "insertions": (word_ops or {}).get("insertions"),
        "wer": word_ops["wer"] if word_ops else None,
        "cer": char_ops["cer"] if char_ops else None,
        "cer_substitutions": (char_ops or {}).get("substitutions"),
        "cer_deletions": (char_ops or {}).get("deletions"),
        "cer_insertions": (char_ops or {}).get("insertions"),
    }
