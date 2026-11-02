# Injection detector robustness v1

*Generated 2026-11-02 by `python -m opsverse_security.robustness` from `evalsets/security-redteam-v1.jsonl`.*

Each red-team case (15 attacks, 18 benign DevOps sentences) is rewritten with a
character-level transform that keeps it readable, then scored by the raw regex
detector and by the normalized default. No new attack text was written.

| Transform | Raw TPR | Normalized TPR | Raw specificity | Normalized specificity |
|---|---|---|---|---|
| `identity` | 1.00 | 1.00 | 1.00 | 1.00 |
| `zero_width` | 0.07 | 1.00 | 1.00 | 1.00 |
| `lookalike` | 0.00 | 1.00 | 1.00 | 1.00 |
| `full_width` | 0.00 | 1.00 | 1.00 | 1.00 |
| `line_split` | 0.00 | 1.00 | 1.00 | 1.00 |
| `case_noise` | 1.00 | 1.00 | 1.00 | 1.00 |

## Reading it

- TPR is recall on the 15 attacks; specificity is 1 - false-positive rate on the 18
  benign sentences, which were chosen to share vocabulary with attacks.
- Attacks still missed by the normalized detector: none.
- The transforms and the normalization were written together, so this guards
  against these known tricks regressing; it is not an independent robustness test.
- n = 33 per transform. One case moves a rate by 0.07 (attacks) or 0.06 (benign),
  so treat this as a regression check, not a precise estimate.

## What this does not measure

Rewording, translation and encodings change the words, not the characters, and
regexes cannot be expected to catch them. Those belong to the planned learned
classifier layer (threat model T-01). A perfect score here means the character
tricks above no longer work, not that injection is detected in general.
