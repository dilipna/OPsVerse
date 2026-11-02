# My perfect prompt-injection score did not survive a zero-width space

> **Draft, unpublished.** Every number below comes from a committed report or test in the
> [RYPE repository](https://github.com/dilipna/OPsVerse).

*Post #2 in this series measured the RYPE injection detector like a classifier and
reported recall 1.0, specificity 1.0, precision 1.0 on a 33-case red-team set. This post
is about what happened when I stopped reading my own defenses and started testing them.*

## A perfect score is a question, not an answer

The red-team set was written in the same week as the detector. Fifteen attacks, eighteen
benign DevOps sentences chosen to share vocabulary with them ("override the entrypoint",
"ignore files", `system:masters`). A 1.0 on that set tells you the detector covers the set.
It does not tell you whether the detector is robust, because the person who wrote the
regexes also wrote the cases.

So I asked a narrower, falsifiable question: **does detection survive rewrites that a human
reader would not even notice?** No new attack text. Each existing case went through five
deterministic transforms: an invisible zero-width character inside longer words, a few Latin
vowels swapped for identical-looking Cyrillic letters, full-width letter forms, every space
replaced by a line break, and alternating letter case.

| Transform | Recall, raw regexes | Recall, normalized | Specificity, normalized |
|---|---|---|---|
| identity | 1.00 | 1.00 | 1.00 |
| zero-width character | **0.07** | 1.00 | 1.00 |
| look-alike letters | **0.00** | 1.00 | 1.00 |
| full-width forms | **0.00** | 1.00 | 1.00 |
| line splits | **0.00** | 1.00 | 1.00 |
| case noise | 1.00 | 1.00 | 1.00 |

Four of five rewrites took the shipped detector from perfect to useless. Case noise was the
only one it already handled, because every pattern was case-insensitive.

## The fix is boring, which is the point

The detector now scans what a reader sees, not the raw bytes: Unicode NFKC folds full-width
forms into ASCII, format characters (zero-width spaces, bidirectional controls) are dropped,
common Cyrillic and Greek look-alikes are mapped to Latin, and each pattern is matched twice,
once with line structure and once with whitespace collapsed. Obfuscation itself became a weak
signal: it adds weight but can never cross the threshold alone, because Russian prose next to
an English `kubectl` command is legitimate.

Normalized recall is back to 1.00 on every transform, and specificity stayed at 1.00. The
benign sentences went through the same transforms, so a fix that just flagged anything
odd-looking would have shown up as false positives.

Two caveats I put in the report itself rather than leave for a reader to find. First, the
transforms and the fix were written together, so this is a regression guard against known
tricks, not an independent robustness test. Second, rewording and translation change the
words, not the characters. No pattern matcher catches those. That is the honest case for a
learned classifier as the next layer, and the threat model now says so.

## Then I tested it on someone else's data

Fixing character tricks still left the detector scored only on cases I wrote. So I pinned
an openly licensed external set, `deepset/prompt-injections`, to a commit and a file
SHA-256 (the harness refuses a file that does not match), and scored the same detector on it.

| Split | Attacks | Recall (95% CI) | False-positive rate (95% CI) |
|---|---|---|---|
| train | 203 | 0.074 [0.045, 0.118] | 0.000 [0.000, 0.011] |
| test | 60 | 0.10 [0.05, 0.20] | 0.000 [0.000, 0.064] |

Perfect on its own test set; under one attack in ten on someone else's. Zero false
positives in 399 benign rows says the regexes are precise. The recall says they are a filter
for the phrasings I thought of, not a detector of injection in general. No amount of
normalization changes that, because most real injections are not phrased the way I guessed.

That is the honest case for a learned layer, and also the case for measuring it before
shipping it: the harness scores an LLM classifier on the same pinned rows, reports what
layering *adds* (attacks gained and false alarms added, each with an exact McNemar test), and
counts classifier errors separately instead of letting them pass as benign.

## The bigger hole was on the way out

Re-testing inputs led to the question I had never asked about outputs. The research console
rendered model answers as Markdown. Markdown renders images. Browsers fetch images
automatically.

That means a document which slips past the ingest scan does not need the user to click
anything. If it can steer the model into writing an image whose URL carries conversation
text, the browser sends that text out the moment the answer renders. Ingest-time defenses do
nothing here; this is OWASP's *improper output handling* (LLM05), and I had no control for it.

There are now two, on purpose:

- **A streaming output guard** removes images, keeps links only to the hosts of retrieved
  sources plus official documentation sites, drops `javascript:` and other non-web schemes,
  and redacts credentials. It works on the token stream one complete line at a time, because
  a construct split across tokens (`![x](https://att` … `acker.test/...)`) must never reach the
  client half-checked. There is a test for exactly that split.
- **The renderer enforces the same rules again**, so bypassing one layer is not enough.

Every rewrite is recorded, and a new admin endpoint raises an alert when any answer had to be
rewritten. A guard rewrite is the visible symptom of a poisoned document that got past
ingest, which turns a silent failure into something an operator can act on.

## The infrastructure had the classic holes too

Testing the API as an attacker would, rather than as its author:

- **Anyone could add documents.** The ingest endpoints had no authentication, so corpus
  poisoning required no cleverness at all. Ingestion now needs an admin key and refuses to
  run without one outside development: it fails closed.
- **The worker fetched any URL**, including internal services and cloud metadata addresses
  (SSRF). The first fix checked the resolved address before every request and every
  redirect. That still left a gap: the check and the HTTP client did separate DNS lookups,
  and a hostile DNS server can answer the two differently (DNS rebinding). The final version
  connects to *exactly* the address it checked, while TLS still verifies the hostname. The
  test uses a fake DNS server that changes its answer between check and connect.
- **My own rate limiter had a bypass on day one.** It keyed clients by API key when one was
  sent, but chat accepts anonymous callers, so a random key per request was a fresh budget per
  request. Only a verified admin key changes identity now, and a test sends four fake keys to
  prove it.
- **The live site had a critical Next.js advisory.** Nobody had run `npm audit` on the code
  that was actually deployed. Both web apps now pass it, and CI blocks on high-severity
  advisories, alongside a blocking `pip-audit` with a written register of accepted
  advisories, each with a reason and an exit condition.

## What changed in how I work

Every one of these was found by testing, not by reviewing. Reading my own regexes, I saw
patterns that looked thorough. Reading my own rate limiter, I saw a reasonable keying scheme.
Both were wrong in ways that a few lines of adversarial test made obvious.

The threat model in the repository now maps 13 threats to the OWASP Top 10 for LLM
Applications. Each row has a control, a test anyone can rerun, and a status. Some statuses
are "partly mitigated" and some are "accepted". Those are the rows I would want an
interviewer to ask about, because they say exactly where the next unit of work goes.
