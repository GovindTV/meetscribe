# Client Terminology Grounding

We handle client-specific domain terminology through a two-stage approach: acoustic decoder conditioning (Whisper initial prompts and hotwords) and synthesis glossary grounding in the Antigravity agent, deliberately omitting intermediate regex transcript normalization.

## Context

Clients and partner projects frequently use proprietary jargon, acronyms, and product names that general-purpose Whisper models transcribe incorrectly or phonetically. We considered a three-stage pipeline incorporating deterministic transcript regex/alias replacement, but rejected regex normalization because managing exhaustive phonetic mishearing mappings introduces unnecessary maintenance overhead and risks false-positive text collisions, whereas the downstream LLM synthesis agent naturally resolves phonetic ambiguities when grounded with domain definitions.

## Decision

1. **Client Glossary Schema**: Maintain structured JSON files under `docs/clients/<client_id>.json` containing canonical terms, descriptions, and hotwords.
2. **ASR Decoder Biasing**: Condition faster-whisper transcription with a formatted `initial_prompt` context sentence and `hotwords` parameter to maximize acoustic accuracy at the source.
3. **Synthesis Glossary Grounding**: Inject the canonical terms and descriptions into the `agy` synthesis prompt to ensure canonical naming and accurate domain context in the generated MoM.
4. **Omission of Transcript Normalization**: Raw transcripts are preserved without regex alias rewriting, leaving disambiguation to the semantic capabilities of the LLM.
5. **Zero MoM Pollution**: Suggested new glossary candidates detected during synthesis are recorded in bundle artifacts and console output, never leaked into the MoM.

## Consequences

- Simplifies glossary maintenance: users only record canonical terms and definitions, without needing to anticipate or maintain lists of phonetic misspellings.
- MoM documents reliably adhere to exact client terminology.
