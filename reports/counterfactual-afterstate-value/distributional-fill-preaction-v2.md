# Distributional fill pre-action student v2 development audit

V2 tested exact pre-action-signature deduplication, whole-stream holdout, and a
confidence fallback to the frozen action-geometry model. All 1,971 inspected
directional discovery rows through seed 57 reduced to 338 unique signatures.

An initial implementation assigned a signature shared by multiple streams to
its first observed stream. That allowed an exact held-out input to remain in
training under another stream name and produced an invalid 97/137 development
result. The audit now records every stream containing a signature and removes
that signature completely whenever any of those streams is held out.

Under the corrected contract, the selected policy is L2 `1000.0` with an
override ratio of `1e30`: it never overrides action geometry. Stream-held-out
CV is 224/350 for both systems. On the 137 globally unique late signatures,
both are 86/137 with 0 wins, 137 ties, and 0 losses. No pre-action v2 candidate
exists under the all-stream nonregression gate.

The proposed permutation-stream confirmation was cancelled before label
collection. New physical confirmation data would not repair a development
candidate that collapses to its baseline. The next model must change its
representation or objective and pass exact-signature stream holdout before any
new holdout is opened.
