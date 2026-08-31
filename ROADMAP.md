# Roadmap

Three follow-on directions, distilled from an internal positioning memo evaluating Aurelius as
a standalone product versus infrastructure. All three reuse pieces that already exist —
`aurelius-mcp`'s OpenAlex→Crossref→arXiv→Semantic Scholar cascade, retraction-awareness,
`verify_stat`, and the 20-agent DAG — as the shared verification engine underneath. Ranked by
priority; each is tracked as a separate issue.

## 1. Verifier API — a language server for claims

A hosted + open-source API that takes AI-generated text and returns claim-by-claim verdicts:
does the citation resolve, is the cited work retracted, does a numeric claim match a registry
(World Bank now, SEC/company filings later). Aimed at builders of AI research/deep-research
agents and RAG apps who need grounding without building their own citation cascade.

This is the same engine `verification.py` and `analyzers/citations.py` already implement,
exposed as stateless endpoints instead of (only) LSP diagnostics. Aurelius IDE becomes the
reference client and distribution funnel rather than the product itself.

## 2. Machine-checkable research-artifact protocol

A signed "verification manifest" spec + tooling that attaches to a paper/preprint and re-runs
its checks (citations resolve, none retracted, claims attributed). Aimed at AI-scientist
tooling and venues that need to prove auto-generated papers are grounded, as arXiv and
conference reviewing absorb more AI-generated submissions and reviews.

The DAG's verification and publication stages become the manifest generator; Aurelius exports
the manifest as one more output format.

## 3. Regulated-research audit-trail layer

An audit-trail + claim-verification layer for AI-assisted investment research, producing the
documentary basis and AI-use disclosure that SEBI's amended RA Regulations require, and the
tamper-evident logging EU AI Act Article 12 requires for high-risk systems. `verify_stat`
extends to financial filings; the DAG's invariants become the audit log.

Veil Finance is the first paying design-partner for this layer — not a separate finance-terminal
product, but the proof-of-revenue customer for the verification engine.

## Sequencing

Start with (1): repackage the existing cascade, retraction check, and `verify_stat` as a public
API with usage metering, and instrument a design partner to emit compliant audit trails
alongside it. If API/developer traction materializes, layer in (2). If the regulated-research
side gets traction instead, deepen (3). Aurelius-the-IDE stays the OSS reference client either
way, not the business.

See the tracking issues for status.
