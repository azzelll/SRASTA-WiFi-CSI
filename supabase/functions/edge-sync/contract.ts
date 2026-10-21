import { z } from 'npm:zod@4.1.5';

const boundedText=z.string().max(240);
const finite=z.number().finite();
const coordinate=finite.min(0).max(1);
const pose=z.object({format:z.literal('movenet-coco17'),keypoints:z.array(z.tuple([coordinate,coordinate,coordinate])).length(17)}).strict();
const event=z.object({id:z.number().int().positive(),event_uid:z.uuid(),timestamp_s:finite,state:z.enum(['normal','standby','inactive','anomaly','critical','suspected_fall','confirmed_fall']),confidence:finite.min(0).max(1),motion_energy:finite,evidence:boundedText,acknowledged_at_s:finite.nullable(),ack_source:boundedText.nullable()}).strict();
const receipt=z.object({id:z.uuid(),event_uid:z.uuid(),action:z.enum(['acknowledge','assistance']),status:z.enum(['applied','expired','rejected']),applied_at_s:finite.nullable(),auto_call:z.literal(false)}).strict();
const snapshot=z.object({
 // Additive fields are optional for older edge releases. Null/unknown means
 // the corresponding head is unavailable, never an inferred empty room.
 presence:z.enum(['unknown','empty','present']).optional(),
 inactivity:z.boolean().nullable().optional(),
 stationary_duration_s:finite.nonnegative().nullable().optional(),
 breathing_condition:z.enum(['sleep','normal','empty']).nullable().optional(),
 schema_version:z.literal(1),updated_at_s:finite,observed_at_s:finite.nullable(),source:z.enum(['live','replay','simulator','unavailable']),simulation:z.boolean(),state:z.enum(['standby','normal','inactive','anomaly','critical']),state_verified:z.boolean(),monitoring_online:z.boolean(),stream_age_s:finite.nullable(),activity:boundedText,motion_energy:finite.nullable(),fall_confidence:finite.min(0).max(1).nullable(),breathing_bpm:finite.min(0).max(60).nullable(),breathing_quality:finite.min(0).max(100),breathing_reason:boundedText,signal_quality:finite.min(0).max(100).nullable(),capture_rate_hz:finite,accepted_frames:z.number().int().nonnegative(),quarantined_frames:z.number().int().nonnegative(),packet_loss_rate:finite.min(0).max(1).nullable(),inference_ms:finite.nullable(),serial_connected:z.boolean(),serial_reconnects:z.number().int().nonnegative(),
 alarm:z.object({requested:z.boolean(),available:z.boolean(),active:z.boolean(),mode:boundedText.optional(),last_error:boundedText.nullable().optional()}).strict(),
 camera:z.object({available:z.boolean(),active:z.boolean(),result:boundedText,
  event_uid:z.uuid().nullable().optional(),
  validations:z.array(z.object({event_uid:z.uuid(),checked_at_s:finite.nonnegative(),outcome:z.enum(['horizontal','not_horizontal','uncertain','error']),result:boundedText,latency_ms:finite.nonnegative(),pose:pose.nullable().optional()}).strict()).max(100).optional()
 }).strict(),
 blynk_connected:z.boolean(),remote:z.object({enabled:z.boolean(),connected:z.boolean(),last_success_s:finite.nullable().optional(),last_error:boundedText.nullable().optional(),worker_running:z.boolean().optional()}).strict(),
 model:z.object({label:boundedText,validation:boundedText,presence_available:z.boolean(),activity_classes_available:z.boolean()}).strict(),events:z.array(event).max(100)
}).strict();

// Keep the summary allowlist shared by the deployed handler and contract tests.
// Raw CSI and arbitrary nested fields must be rejected rather than discarded.
export const payload=z.object({device_id:z.uuid(),snapshot,events:z.array(event).max(100),receipts:z.array(receipt).max(100)}).strict();
