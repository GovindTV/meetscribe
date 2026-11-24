# Bilingual and Code-Switched Meeting Support (Hindi & English)

We support meetings spoken in mixed Hindi and English (Hinglish / code-switching) through bilingual ASR decoder conditioning, Devanagari punctuation cleaning, and LLM-driven translation into executive English during agent synthesis, rather than relying on Whisper's internal translation head.

## Context

Technical and delivery teams frequently communicate using intra-sentential and inter-sentential code-switching (Hinglish), mixing Hindi grammar and conversational phrasing with English technical terms (APIs, schemas, Snowflake tables, pull requests). 

We evaluated two architectural approaches:
1. **Whisper Translate Mode (`task="translate"` at ASR time)**: Whisper's single-pass speech translation head often compresses sentences, drops subtle technical details, and struggles when speakers rapidly toggle between languages or use English technical loanwords.
2. **ASR Transcription + LLM Synthesis Translation (Chosen)**: Whisper transcribes verbatim using Hindi language conditioning (`--language hi --task transcribe`) and a bilingual `initial_prompt`. The downstream Antigravity LLM synthesis agent (`agy`) then translates Hindi context into executive English while preserving English technical terms and applying silent omission to colloquial small talk.

## Decision

1. **ASR Language and Task Configuration**: Expose `--language` (e.g. `hi`, `en`) and `--task` (`transcribe`, `translate`) CLI options in `process_meeting.py`, defaulting to auto-detection and transcription.
2. **Bilingual Decoder Biasing**: When `language="hi"` is configured, condition Whisper with a bilingual `initial_prompt` prefix (`"यह मीटिंग हिंदी और अंग्रेज़ी में है (Hinglish discussion)..."`) alongside client domain terms to prime the acoustic decoder for both Devanagari and Latin script tokens.
3. **Punctuation Support**: Extend transcript repetition cleaning (`clean_repetitive_text`) to recognize Devanagari sentence terminators (Purna Viram `।` and double Purna Viram `॥`).
4. **Synthesis Translation & Silent Omission**: Instruct the Antigravity synthesis agent to synthesize the entire Minutes of Meeting into professional executive English, translating Hindi discussion points while preserving technical nomenclature and silently omitting Hindi conversational filler with zero meta-commentary.
5. **Team Roster Disambiguation**: Map any Devanagari or phonetic transliterated attendee names back to canonical Latin forms from the Known Project Team Roster.

## Consequences

- High-fidelity preservation of technical discussions, architectural debates, and action items regardless of the spoken language.
- Executive MoM documents remain uniformly in professional English.
- No loss of domain terminology or acoustic hallucination caused by language detection lock-in.
