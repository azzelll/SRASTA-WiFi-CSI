import type { Device } from './types';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function notificationRoute(search: string): {device: string; event: string} {
  const query = new URLSearchParams(search);
  const device = query.get('device') || '', event = query.get('event') || '';
  return {device: uuid.test(device) ? device : '', event: uuid.test(event) ? event : ''};
}
export function authorizedNotificationDevice(devices: Device[], requested: string): string {
  return devices.find(device => device.id === requested)?.id || '';
}
