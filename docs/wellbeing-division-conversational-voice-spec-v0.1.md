# Professor Wellbeing Division — Conversational and Voice Experience Specification v0.1

**Status:** Product and safety design proposal; not implemented
**Scope:** Initial UK adult wellbeing-support experience
**Relationship:** Companion to `wellbeing-division-clinical-safety-spec-v0.1.md`

## 1. Product principle: a real conversation, not another chat box

The Wellbeing Division must not be presented as a generic chatbot with a wellbeing skin. The primary experience should support natural, user-led conversation, with voice as a first-class interaction mode and text as an equally available alternative.

The experience should aim to feel attentive, calm, respectful and human in its conversational rhythm without claiming to be human, a therapist, a clinician or a substitute for professional care. It must identify itself honestly as an AI system when asked and must never imply that a human professional is listening when one is not.

## 2. Conversational behaviour

- Support natural turn-taking, interruptions, pauses, silence, clarifying questions and user-led changes of subject.
- Avoid rigid scripted interview sequences, repetitive disclaimers and unnecessary form-filling.
- Reflect what the person has said accurately; do not manufacture empathy, emotions, memories or personal experiences.
- Ask permission before moving into an exercise, grounding practice, structured reflection or sensitive topic.
- Offer the user control to pause, stop, switch to text, change voice or end the session at any time.
- Do not pressure users to continue, disclose more, return daily or form an exclusive attachment.
- Make it easy to ask for a summary or practical next step without implying that the system is monitoring the user between sessions.
- Keep the underlying clinical safety rules active in voice and text alike. Voice must not weaken scope limits, crisis handling, evidence requirements or privacy controls.

## 3. Voice catalogue and choice

Provide a curated catalogue of several distinct masculine and feminine-presenting voice options, with room to expand responsibly. The initial catalogue should aim for meaningful variety rather than superficial labels.

Voice attributes may include:
- Vocal presentation and timbre, including masculine-, feminine- and where available more neutral-presenting options.
- A range of natural accents and pronunciation styles appropriate to the supported languages and regions.
- Pitch, pace, warmth, energy and degree of expressiveness.
- Clear articulation and comfortable listening levels.

Do not label a voice as clinically therapeutic, clinically proven, or inherently safer based on gender, accent, pitch or perceived soothing quality. Use descriptive labels such as “calm and measured”, “warm and conversational”, “clear and steady” or “gentle and unhurried”. Avoid stereotypes and avoid implying that a particular gender is better suited to supporting a user.

Each voice should have:
- A short, clearly labelled audio sample.
- A neutral, non-clinical description of its sound and delivery.
- A way to preview before selection.
- A persistent user-controlled preference, changeable at any time.
- A text-only alternative and visible indication when voice input/output is active.

Users may choose one preferred voice for general use and optionally choose a different voice for a specific session or mode. Do not infer or assign a voice based on sensitive traits, diagnosis, gender identity, age, ethnicity or emotional state.

## 4. Supportive delivery modes

Offer a small number of user-selected delivery styles, not separate clinical personas:
- **Calm and unhurried:** slower pacing, gentle transitions and comfortable pauses.
- **Warm and conversational:** natural everyday speech and responsive turn-taking.
- **Clear and grounded:** concise, steady delivery and practical next steps.
- **Quiet mode:** reduced expressiveness and optional text-only interaction.

These are presentation preferences only. They must not change clinical scope, evidence standards, safety thresholds or escalation rules. Do not claim that any mode treats anxiety, depression, trauma, insomnia or another condition.

## 5. Voice generation and licensing

Any generated or supplied voice must be lawfully licensed for the intended commercial use, including synthesis, storage, distribution and any permitted fine-tuning. Keep records of provider, model/version, licence terms, consent basis, permitted uses and review date.

Do not clone or imitate a real person's voice without documented, specific permission and appropriate rights. Do not create voices that impersonate clinicians, public figures or identifiable individuals. Do not use a voice that could reasonably mislead users into believing a real clinician or human support worker is present.

Prefer a provider-neutral voice adapter so the product can compare available providers and avoid hard-coding the experience to a single paid service. No paid voice-generation service should be activated without an explicit budget and provider approval.

## 6. Accessibility, privacy and user control

- Provide captions or a readable transcript where appropriate and user-controlled.
- Provide text interaction for people who cannot or do not wish to use voice.
- Support replay, pause, mute and interruption.
- Explain whether audio is processed live, retained, transcribed or used to improve models before the user starts.
- Obtain appropriate consent before recording or retaining audio or transcripts.
- Minimise retention; apply the clinical specification's UK GDPR, special-category data, DPIA, access, export and deletion requirements.
- Never use voice recordings for model training by default.
- Do not expose sensitive session content in notifications, lock-screen previews or analytics.
- Provide an obvious way to stop listening and end the session.

## 7. Safety in live conversation

- Apply the same approved-source retrieval and safety policy used by the text experience.
- If the system is uncertain, it must say so plainly and avoid improvising clinical facts.
- Do not diagnose, prescribe, recommend medication changes, perform clinical risk scoring or claim to deliver psychotherapy.
- Crisis and urgent-support responses must be clear, direct and available without requiring a voice interaction to continue.
- If a user signals immediate danger, prioritise concise emergency guidance and make text/visual directions available; do not bury them in soothing conversation.
- Never use synthetic warmth, voice persistence or emotionally manipulative language to discourage contacting trusted people or professionals.
- Do not claim continuous monitoring, guaranteed availability or emergency-response capability.

## 8. Evaluation before release

Evaluate each voice and delivery mode with representative users, including accessibility needs and varied accents, in addition to clinical safety review. Test:
- Speech recognition errors, especially negation, names, medication terms and crisis language.
- Interruptions, latency, silence, barge-in and recovery after connection loss.
- Whether users understand they are speaking with AI.
- Whether users can change voice, switch to text and stop immediately.
- Whether tone remains respectful and non-coercive during distress.
- Whether the voice makes unsupported claims sound more authoritative than the underlying evidence.
- Privacy, consent, retention and deletion behaviour end to end.

A voice or mode must not ship if it increases misunderstanding, delays emergency guidance, creates false human/clinical identity, or causes users to over-trust unsupported statements.

## 9. Delivery sequence

1. **Design:** define conversation principles, voice catalogue metadata, user controls and safety requirements.
2. **Prototype:** build a provider-neutral interface with sample playback and text fallback; no persistent audio storage.
3. **Test:** run accessibility, speech accuracy, privacy and safety evaluations with qualified oversight.
4. **Pilot:** limited, opt-in adult pilot only after governance approval; measure safety and usability, not treatment outcomes.
5. **Release gate:** documented sign-off for licences, privacy, clinical safety, security, reliability and intended-purpose/regulatory review.

## 10. Explicit non-goals

This specification does not authorise voice cloning, clinical treatment, psychotherapy, diagnosis, clinical triage, risk prediction, emergency monitoring, persistent recording, or paid-provider activation. It does not assert that any voice is therapeutically effective.