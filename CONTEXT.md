# MoM Pipeline

Pipeline for converting video meeting recordings into comprehensive Minutes of Meeting using audio extraction, transcription, visual artifact capture, and agent synthesis.

## Language

**Recording**:
The source meeting video file captured from a video conference or screen recording.
_Avoid_: Video file, meeting capture, input file

**Split Recording**:
A sequence of two or more recording files belonging to the same continuous meeting session (e.g. created by OBS auto-split or recording pauses).
_Avoid_: Video parts, video chunks, segmented files

**Session Timeline**:
The unified continuous chronological timeline created by concatenating split recording segments into a single cohesive stream.
_Avoid_: Merged video, stitched timeline, joined session

**Artifact Bundle**:
The temporary working directory containing intermediate extracted media (audio, transcript, slide frames, speaker frames) for a single meeting processing run.
_Avoid_: Output folder, temp files, work directory

**Transcript**:
The time-indexed textual record of meeting audio containing utterance text along with start and end timestamps.
_Avoid_: Subtitles, captions, speech-to-text dump

**Speech Turn**:
A contiguous block of speech by an individual participant identified in the transcript with a start and end timestamp.
_Avoid_: Utterance segment, speech snippet, audio chunk

**Slide Frame**:
An extracted visual image capturing a distinct slide, document, or screen-share change during the meeting.
_Avoid_: Screenshot, picture, snapshot

**In-Meeting Screenshare**:
Visual presentation material (slides, spreadsheets, dashboards) actively shared within the conference call and verbally discussed by participants.
_Avoid_: Desktop recording, monitor view, screen capture

**Local Desktop Activity**:
Background applications, browser tabs, development environments, or multitasking visible on the recording host computer that were not shared or discussed in the meeting. Must be strictly excluded from the MoM.
_Avoid_: Unshared windows, personal screen, host multitasking

**Speaker Frame**:
An image captured at the onset timestamp of a speech turn to visually identify the speaker tile or active speaker highlight.
_Avoid_: Webcam picture, speaker photo, face crop

**Speaker Tile**:
A visual webcam feed or avatar box in the meeting UI indicating attendee identity and active speaker state.
_Avoid_: Webcam box, face camera, participant video

**Minutes of Meeting (MoM)**:
The official structured markdown document detailing attendees, chronological discussion context, decisions made, and assigned action items agreed upon by meeting participants. Never includes the recording host unshared local desktop activity.
_Avoid_: Meeting notes, transcript summary, meeting log, surveillance record

**Silent Omission**:
The absolute exclusion of non-meeting context (informal pleasantries, weather/commute banter, personal anecdotes, unshared workstation windows) without generating any trace, summary bullet, or time-block in the document.
_Avoid_: Conditional omission, commented omission, partial exclusion

**Zero Meta-Commentary**:
The strict rule prohibiting disclaimers, explanatory notes, or parentheticals stating what was omitted or ignored (e.g. prohibiting phrases like "Note: social pleasantries regarding X have been excluded").
_Avoid_: Omission disclaimers, exclusion notes, explanatory footnotes

**Multi-Track Recording**:
A recording configuration that captures audio across distinct physical streams (Track 1: Master Mix, Track 2: Remote Attendees, Track 3: Local Host Mic).
_Avoid_: Split audio, channel dump, raw audio

**Speaker Channel**:
The designated physical audio stream identifying whether a speech turn originated from the local recording host or external remote call participants.
_Avoid_: Voice channel, track name, audio source

**Client Glossary**:
A structured repository of canonical client terminology, domain definitions, and hotwords used to enforce vocabulary consistency across transcription and meeting synthesis.
_Avoid_: Wordlist, dictionary, cheat sheet, vocab file

**Decoder Biasing**:
The conditioning of speech-to-text acoustic token prediction probabilities using initial prompts and hotwords during audio transcription.
_Avoid_: Prompt hacking, prompt injection, Whisper seeding

**Synthesis Glossary Grounding**:
The injection of canonical client vocabulary and domain descriptions into the meeting synthesis prompt to resolve acoustic ambiguities and ensure accurate terminology in the MoM.
_Avoid_: Prompt context, background notes, reference injection

