# SRASTA x GEMASTIK XIX 2026 - delivery checklist

Source: [*Pedoman Pagelaran Mahasiswa Nasional Bidang TIK Tahun
2026*](sources/gemastik-2026-guidelines.pdf), provided by the team. This file
turns the applicable **Piranti Cerdas, Sistem Benam & IoT** rules into a
working checklist; the supplied PDF remains the authoritative competition
document if a later announcement differs.

## Competition fit

The [SRASTA product proposal](https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit) is the immutable source of
truth for scope, features, and product claims. This checklist may map that
proposal to GEMASTIK deliverables, but it may never narrow, replace, defer, or
reinterpret it.

SRASTA must visibly implement all three category elements:

| Element | SRASTA evidence |
| --- | --- |
| Kecerdasan | Train-only motion-feature Random Forest sanity check; final TCN-Lite inference on `[time, 52]` CSI amplitude windows. |
| Sistem benam | ESP32-S3 receiver, versioned CSI frame contract, fixed decoder, and Raspberry Pi-compatible edge runtime. |
| IoT | Local FastAPI monitoring API, SQLite event log, and optional rate-limited Blynk notification adapter. |

The current WiFi-CSI baseline is evidence for one implementation path. It is
not a reason to remove, demote, or dispute any product feature stated in the
proposal.

## Penyisihan deliverables

- [ ] Originality/copyright declaration, signed by the team leader on stamp
  duty, PDF, maximum 2 MB.
- [ ] Proposal PDF, maximum **30 pages total** and maximum **10 MB**, using the
  required filename `GEMASTIK XIX Piranti Cerdas - <ID-Tim> - <Nama Tim> -
  <Judul Karya> - Proposal.pdf`.
- [ ] Proposal cover: innovation title, team/participants, Kemendiktisaintek
  logo on the upper left, GEMASTIK XIX/2026 and university logos on the upper
  right.
- [ ] Proposal sections: abstract; background; urgency and benefits; method
  showing AI, embedded, and IoT; prototype/model design (hardware, power,
  sensor specifications, circuit, 3D design); functional/workflow/performance
  analysis; completed and remaining implementation plan; 50% prototype photos
  and explanations; development-video link; references.
- [ ] Unlisted YouTube development video: MP4, 720p, maximum **3 minutes**,
  GEMASTIK teaser/intro at the beginning and/or end, clear audio/visuals,
  explanatory running text, and narrator visible. It must show a useful
  problem solution, the three category elements, and at least **50% progress**.
- [ ] Upload deadline stated in the supplied guide: **8 August 2026, 23:59
  WIB**. Reconfirm in the competition portal before submission.

## Evaluation focus

The proposal should make the judging criteria easy to locate:

| Penyisihan criterion | Weight | SRASTA response |
| --- | ---: | --- |
| Creativity: urgency, novelty/state of the art, and three-element application | 30% | Contactless privacy-preserving sensing plus an explicit end-to-end edge architecture. |
| Proposal writing: format and substance | 30% | Use the required section order and distinguish verified evidence from planned work. |
| Potential benefit to society | 20% | Faster caregiver awareness for a possible indoor fall while preserving privacy. |
| Feasibility | 20% | Show working replay/demo, traceable data protocol, affordable components, and a bounded V1 scope. |

For the final, make the evidence legible for intelligence, functional problem
solving, design/model implementation, effectiveness/efficiency/cost/adaptability,
and presentation/demo (each 20%). Prepare the code for review when requested.

## Evidence hygiene

- Use the curated ESP32 manifest for baseline training. Do not upload or add
  CSI recordings, model artifacts, tokens, or participant data to Git.
- Report only grouped clip-level proxy metrics from the current curated data.
  Event metrics, false alerts/hour, packet drop, and empirical state latencies
  stay `not_available` until continuous ESP32-S3 captures and annotations exist.
- Present `suspected_fall` and `confirmed_fall` as separate states. A
  confirmation that requires inactivity cannot claim the same latency as a
  motion trigger.
- External WiFall and ESP-Fi HAR data are transfer-learning/ablation sources
  only; never fold them into the main SRASTA test split or final claim.
