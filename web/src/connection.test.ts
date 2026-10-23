import { afterEach, describe, expect, it, vi } from 'vitest';

const client = vi.hoisted(() => ({rpc:vi.fn(),from:vi.fn()}));
const createClient = vi.hoisted(() => vi.fn(() => client));
vi.mock('@supabase/supabase-js', () => ({createClient}));

async function load(mode:string,key='sb_publishable_test') {
 vi.resetModules();
 vi.stubEnv('VITE_ACCESS_MODE',mode);
 vi.stubEnv('VITE_SUPABASE_URL','https://test.supabase.co');
 vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY',key);
 return import('./connection');
}
afterEach(() => {vi.unstubAllEnvs();vi.clearAllMocks();});

describe('dashboard access boundary', () => {
 it('reads the public device and snapshot RPCs without a user session or table query', async () => {
  const connection=await load('public');
  const devices=[{id:'selected-device',label:'SRASTA Edge'}];
  const state={snapshot:null,receipts:[]};
  client.rpc.mockResolvedValueOnce({data:devices,error:null}).mockResolvedValueOnce({data:state,error:null});
  expect(await connection.listDevices()).toEqual(devices);
  expect(await connection.remoteState('selected-device')).toEqual(state);
  expect(client.rpc.mock.calls).toEqual([['list_public_devices'],['read_public_dashboard',{p_device_id:'selected-device'}]]);
  expect(client.from).not.toHaveBeenCalled();
  expect(createClient).toHaveBeenCalledWith('https://test.supabase.co','sb_publishable_test',{
   auth:{persistSession:false,autoRefreshToken:false,detectSessionInUrl:false},
  });
 });
 it('sends both actions without substituting or inventing a caregiver identity', async () => {
  const connection=await load('public');
  for(const action of ['acknowledge','assistance'] as const) {
   const receipt={id:action,event_uid:'event',action,status:'pending',applied_at_s:null};
   client.rpc.mockResolvedValueOnce({data:receipt,error:null});
   expect(await connection.sendCommand('device','event',action,action)).toEqual(receipt);
   expect(client.rpc).toHaveBeenLastCalledWith('request_public_caregiver_command',{p_id:action,p_device_id:'device',p_event_uid:'event',p_action:action});
  }
 });
 it('rejects a revoked public dashboard instead of falling back to local data', async () => {
  const connection=await load('public');
  client.rpc.mockResolvedValueOnce({data:null,error:null});
  await expect(connection.remoteState('revoked')).rejects.toThrow('belum tersedia');
 });
 it('preserves authenticated command routing when cloud mode is selected', async () => {
  const connection=await load('cloud');
  client.rpc.mockResolvedValueOnce({data:{status:'pending'},error:null});
  await connection.sendCommand('device','event','acknowledge','command');
  expect(client.rpc).toHaveBeenCalledWith('request_caregiver_command',{p_id:'command',p_device_id:'device',p_event_uid:'event',p_action:'acknowledge'});
  expect(createClient).toHaveBeenCalledWith('https://test.supabase.co','sb_publishable_test',undefined);
 });
 it('never initializes the browser client with an admin secret', async () => {
  const connection=await load('public','sb_secret_forbidden');
  expect(connection.cloudConfigured).toBe(false);
  expect(connection.cloud).toBeNull();
  expect(createClient).not.toHaveBeenCalled();
 });
});
