# Caregiver UI from SRASTA Figma — 9 October 2026

## Reference and implementation

Source: https://www.figma.com/design/FMeAWEMhR064JwZ5XgriiN/SRASTA?node-id=5-155

The selected alert-history card belongs to the dashboard page. Implementation follows high fidelity MCP context and screenshots for five parent frames: `5:2` standby, `5:185` normal, `5:370` inactive, `5:555` anomaly, and `5:737` critical. The app uses the existing React, TypeScript, and plain CSS stack.

Sidebar, header, room illustration, state card, camera panel, six metric cards, chart, and alert history follow the supplied layout. Original Figma vectors and illustrations are served locally under `web/public/figma/`. Inter is self hosted with its OFL license.

Navigation includes Beranda, Riwayat Aktivitas, Riwayat Peringatan, Perangkat, Pengaturan, and Tentang Sistem. Profile, device selection, authentication, push setup, acknowledgement, assistance, notification routing, and emergency contact actions remain connected to the existing contract.

## Data boundaries

Example names, timestamps, activities, RSSI, inactivity threshold, notification delivery statements, and waveforms are not hardcoded as real output. The app renders available edge data. Signal quality uses the published percentage because the snapshot has no raw RSSI field. Fall confidence is labeled as fall score rather than activity confidence.

Freshness/source labels remain visible. Stale readings do not imply active monitoring. ACK does not clear critical state. Camera results require a matching event UID and live source; uncertain/failed results remain distinct. Pose artwork is explicitly labeled illustration.

## Verification

- `npm test`: 17 tests passed across five files, including seven dashboard evidence-boundary cases.
- `npm run build`: TypeScript and Vite production build passed.
- Browser verification used isolated, visibly labeled UI fixtures. No fixture snapshot or command was written to production cloud or Pi.
- At 1536 px, all five states match reference panel geometry: state `(288,196,560,288)`, camera `(870,236,585,238)` or 250 px tall while processing, metrics `(288,506,1148,158)`, chart `(288,686,665,360)`, history `(982,686,466,360)`.
- All five states at 390 px have no horizontal overflow or broken image. A 360 px phone and 1280 px tablet were also checked.
- 52 visible unique static assets were nonempty, loaded, and rendered at SVG intrinsic dimensions; the dropdown arrow rotates in its wrapper.
- Profile save, device navigation, graph range selection, alert navigation, and an isolated ACK receipt were checked in the browser.
- Actual CSI/camera operation on Pi was not tested during this UI task.

Evidence: `artifacts/figma/20261009-ui-reference/`, including screenshots, geometry, and asset audit. The temporary fixture was moved outside deployment source after testing.

## Deployment ownership

Vercel account verified as `madeshandykrisnanda@gmail.com` (`azzelll`), project `srasta-caregiver`, ID `prj_ZGLuSEAgmr09gpgTLcteN65Di16T`, team `team_YT0FhWq3pnR5pqA8tT7dXrVu`.

Production URL: https://srasta-caregiver.vercel.app

Deployment `dpl_6ugWb9dE8Yy9R7oEJJ7RfDxiLTry` is READY under the verified team/project. Production HTML responds 200; the served CSS hash matches the local build. All 52 visible image assets, the font, and service worker passed HTTP/MIME/content checks (54 checks). The production login rendered on desktop and 390 px mobile; the email/password toggle worked without submitting credentials, and no console error or broken image was observed. Authenticated dashboard behavior remains verified through the isolated fixtures, not a fresh production login or live hardware session.
