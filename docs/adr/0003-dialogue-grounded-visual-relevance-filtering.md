# Dialogue-Grounded Visual Relevance Filtering for MoM Synthesis

Desktop recording software (such as OBS) captures the local host machine screen, which often records private desktop applications, background browser tabs, or multitasking unrelated to the meeting conference call. A Minutes of Meeting (MoM) is an official record of meeting proceedings—not a surveillance log of the recording host workstation. We decided to enforce strict dialogue-grounded visual filtering: visual artifacts from the recording must only be included in the MoM if they are directly corroborated by in-meeting verbal dialogue (e.g. an attendee actively presenting and discussing a shared document or slide).

## Considered Options

- **Naive Multimodal Logging**: Documenting every on-screen window, browser tab, or application transition observed in the video. Rejected because it exposes the recorder personal desktop activity, records unrelated private work, and hallucinates non-meeting actions as meeting deliverables.
- **Pure Audio Synthesis**: Ignoring visual frames entirely. Rejected because genuine screenshares (such as presentation slides, architecture diagrams, and review spreadsheets) provide indispensable technical context when attendees reference on-screen data.
- **Dialogue-Grounded Visual Filtering**: Visual frames are cross-referenced with verbal dialogue. Visual content is documented only when verbal discussion confirms it was presented to and discussed by meeting attendees.

## Consequences

- The agent prompt explicitly instructs the scribe to distinguish between shared in-meeting presentations and the recording host local desktop/multitasking.
- Incidental windows (IDEs, background web portals, local tools) are silently discarded.
- Action items and presentation summaries reflect only true meeting commitments and shared deliverables.
