import { describe, expect, it } from 'vitest';
import { authorizedNotificationDevice, notificationRoute } from './notification-route';

describe('notification route', () => {
  const device = '00000000-0000-4000-8000-000000000001';
  const event = '00000000-0000-4000-8000-000000000021';
  it('retains the target event and chooses only a device visible to the caregiver', () => {
    expect(notificationRoute(`?device=${device}&event=${event}`)).toEqual({device, event});
    expect(authorizedNotificationDevice([{id: device, label: 'Assigned'}], device)).toBe(device);
    expect(authorizedNotificationDevice([{id: device, label: 'Assigned'}], event)).toBe('');
  });
  it('does not interpret malformed IDs as URLs or markup', () => {
    expect(notificationRoute('?device=https://example.com&event=<script>')).toEqual({device: '', event: ''});
  });
});
