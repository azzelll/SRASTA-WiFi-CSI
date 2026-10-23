export type SystemState = 'standby' | 'normal' | 'inactive' | 'anomaly' | 'critical';
export interface CareEvent { id:number; event_uid:string; timestamp_s:number; state:string; confidence:number; motion_energy:number; evidence:string; acknowledged_at_s:number|null; ack_source:string|null; }
export interface CameraPose {format:'movenet-coco17';keypoints:[number,number,number][];}
export interface CameraValidation {event_uid:string;checked_at_s:number;outcome:'horizontal'|'not_horizontal'|'uncertain'|'error';result:string;latency_ms:number;pose?:CameraPose|null;}
export interface Snapshot {
 presence?:'unknown'|'empty'|'present'; inactivity?:boolean|null; stationary_duration_s?:number|null; breathing_condition?:'sleep'|'normal'|'empty'|null;
 schema_version:1; updated_at_s:number; observed_at_s:number|null; source:'live'|'replay'|'simulator'|'unavailable'; simulation:boolean; state:SystemState; state_verified:boolean; monitoring_online:boolean; stream_age_s:number|null; activity:string; motion_energy:number|null; fall_confidence:number|null; breathing_bpm:number|null; breathing_quality:number; breathing_reason:string; signal_quality:number|null; capture_rate_hz:number; accepted_frames:number; quarantined_frames:number; packet_loss_rate:number|null; inference_ms:number|null; serial_connected:boolean; serial_reconnects:number; alarm:{requested:boolean; available:boolean; active:boolean; mode?:string}; camera:{available:boolean; active:boolean; result:string;event_uid?:string|null;validations?:CameraValidation[]}; blynk_connected:boolean; remote:{enabled:boolean;connected:boolean}; model:{label:string;validation:string;presence_available:boolean;activity_classes_available:boolean}; events:CareEvent[];
}
export interface CommandReceipt {id:string; event_uid:string; action:'acknowledge'|'assistance'; status:'pending'|'applied'|'expired'|'rejected'; applied_at_s?:number|null; }
export interface Device {id:string; label:string; }
