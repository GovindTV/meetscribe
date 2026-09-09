# Silent Omission of Non-Meeting Context and Zero Meta-Commentary

When synthesizing Minutes of Meeting (MoM), non-meeting elements (informal pleasantries, weather/commute banter, personal anecdotes, local workstation windows) must be omitted without leaving any meta-commentary, exclusion disclaimers, or pseudo-agenda sections.

## Context

When models are instructed to omit non-meeting content, they often exhibit a failure mode where they insert explanatory disclaimers such as `*(Note: Social pleasantries regarding regional weather in Jaipur/Noida have been excluded)*` or describe unshared local desktop windows while asserting they are omitted. This meta-commentary paradoxically documents and calls attention to the exact private or informal context that should never appear in an executive document. Additionally, models sometimes fabricate pseudo-agenda sections (e.g. `Workspace Context & Operational Sync`) or formal action items out of casual conversational remarks.

## Decision

We enforce **Strict Silent Omission** across prompt instructions and pipeline post-processing:

1. **Zero Meta-Commentary**: Never output notes, disclaimers, or parentheticals indicating that content was omitted, skipped, or excluded.
2. **Total Invisibility**: Excluded topics (weather, traffic, personal life, unshared desktop tools) must leave zero footprint in the text—their names, locations, and subjects must never appear.
3. **No Pseudo-Agenda Blocks**: Time intervals occupied solely by small talk or conversational pauses must not receive a section header or bullet point in discussion summaries. The timeline advances directly to the next substantive business or technical discussion.
4. **Clean Presentation Section**: If no screenshare or slide deck was presented in the meeting call, Section 2 must simply state: `None. No presentation slides, documents, or screenshares were presented during this session.` Internal frame filenames and unshared host applications must never be listed or described.
5. **Legitimate Action Items Only**: Action items must strictly capture actionable project and engineering commitments. Casual comments (e.g., walking to a desk, leaving a cabin) must never be converted into action items.
6. **Programmatic Sanitizer**: `process_meeting.py` implements an automated regex cleaner to strip any accidental exclusion disclaimers before persisting the final markdown document.

## Consequences

- MoM documents remain professional, concise, and focused solely on genuine meeting business.
- Private host details and casual banter are completely protected and never leaked into documentation.
